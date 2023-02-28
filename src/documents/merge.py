import logging
import os
import re
import tempfile

from celery import chord
from celery import group
from documents import tasks
from documents.models import Document
from pikepdf import Pdf


logger = logging.getLogger("paperless.merge")


class MergeError(Exception):
    pass


class PdfCache:
    def __init__(self):
        self.cache = dict()

    def open_from_document(self, document: Document):
        if document.pk in self.cache:
            return self.cache[document.pk]

        if document.mime_type == "application/pdf":
            filename = document.source_path
        elif document.has_archive_version:
            filename = document.archive_path
        else:
            raise MergeError(f"Document {document.pk} does not have a PDF.")

        if not os.path.exists(filename):
            raise MergeError(f"{filename} does not exist.")

        pdf = Pdf.open(filename)
        self.cache[document.pk] = pdf

        return pdf

    def close_all(self):
        for pk in self.cache:
            self.cache[pk].close()

        self.cache.clear()


def parse_page_list(page_list: str):

    if not page_list:
        return []

    result = []

    re_simple = re.compile(r"^\d+$")
    re_range = re.compile(r"^(\d+)-(\d+)$")

    for page_list_part in page_list.split(","):
        match_simple = re_simple.match(page_list_part)
        match_range = re_range.match(page_list_part)
        if match_simple:
            result.append(int(page_list_part))
        elif match_range:
            first = int(match_range.group(1))
            last = int(match_range.group(2))
            if first <= last:
                result.extend(range(first, last + 1))
            else:
                result.extend(reversed(range(last, first + 1)))
        else:
            raise MergeError(f"Invalid page range: {page_list}")

    return result


def copy_pdf_metadata(source: Pdf, target: Pdf):
    with source.open_metadata() as source_meta:
        with target.open_metadata() as target_meta:
            for k in source_meta:
                try:
                    target_meta[k] = source_meta[k]
                except TypeError:
                    # TODO: https://github.com/pikepdf/pikepdf/issues/188
                    logger.warning(
                        f"Could not copy metadata {k} while " f"merging documents",
                        exc_info=True,
                    )


def copy_document_metadata(document: Document, consume_task):
    if document.correspondent:
        consume_task["override_correspondent_id"] = document.correspondent.id
    if document.document_type:
        consume_task["override_document_type_id"] = document.document_type.id
    if document.tags.count() > 0:
        consume_task["override_tag_ids"] = [tag.id for tag in document.tags.all()]

    consume_task["override_date"] = document.created


def execute_split_merge_plan(
    plan,
    tempdir: str,
    metadata: str = "redo",
    delete_source: bool = False,
    preview: bool = True,
):

    consume_tasks = []
    cache = PdfCache()
    source_documents = set()

    try:
        for target_doc_spec in plan:
            # create a new document from documents in target_doc_spec

            target_pdf: Pdf = None
            try:
                target_pdf = Pdf.new()
                target_pdf_filename = tempfile.NamedTemporaryFile(
                    prefix="merge_",
                    suffix="_pdf",
                    dir=tempdir,
                ).name
                version = target_pdf.pdf_version
                consume_task_kwargs = {}

                for (i, source_doc_spec) in enumerate(target_doc_spec):
                    source_document_id = source_doc_spec["document"]
                    source_documents.add(source_document_id)

                    if "pages" in source_doc_spec:
                        pages = parse_page_list(source_doc_spec["pages"])
                    else:
                        pages = None

                    try:
                        source_document: Document = Document.objects.get(
                            id=source_document_id,
                        )
                    except Document.DoesNotExist:
                        raise MergeError(
                            f"Document {source_document_id} does not exist.",
                        )

                    source_pdf: Pdf = cache.open_from_document(source_document)
                    version = max(version, source_pdf.pdf_version)

                    if i == 0:
                        # first source document for this target
                        consume_task_kwargs["override_title"] = source_document.title
                        copy_pdf_metadata(source_pdf, target_pdf)
                        if metadata == "copy_first":
                            copy_document_metadata(
                                source_document,
                                consume_task_kwargs,
                            )

                    if pages is not None:
                        for page in pages:
                            if page > len(source_pdf.pages) or page < 1:
                                raise MergeError(
                                    f"Page {page} is out of range.",
                                )
                            target_pdf.pages.append(source_pdf.pages[page - 1])
                    else:
                        target_pdf.pages.extend(source_pdf.pages)

                target_pdf.remove_unreferenced_resources()
                target_pdf.save(target_pdf_filename, min_version=version)
                target_pdf.close()

                consume_tasks.append(
                    tasks.consume_file.s(target_pdf_filename, **consume_task_kwargs),
                )
            finally:
                if target_pdf is not None:
                    target_pdf.close()
    finally:
        cache.close_all()

    if not preview:

        if delete_source:
            chord(
                header=consume_tasks,
                body=tasks.delete_documents_callback.s(list(source_documents)),
            ).delay()
        else:
            group(consume_tasks).delay()

    return [t.args[0] for t in consume_tasks]
