import logging
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile

import dateparser
import magic
from django.conf import settings
from django.utils import timezone

# This regular expression will try to find dates in the document at
# hand and will match the following formats:
# - XX.YY.ZZZZ with XX + YY being 1 or 2 and ZZZZ being 2 or 4 digits
# - XX/YY/ZZZZ with XX + YY being 1 or 2 and ZZZZ being 2 or 4 digits
# - XX-YY-ZZZZ with XX + YY being 1 or 2 and ZZZZ being 2 or 4 digits
# - ZZZZ.XX.YY with XX + YY being 1 or 2 and ZZZZ being 2 or 4 digits
# - ZZZZ/XX/YY with XX + YY being 1 or 2 and ZZZZ being 2 or 4 digits
# - ZZZZ-XX-YY with XX + YY being 1 or 2 and ZZZZ being 2 or 4 digits
# - XX. MONTH ZZZZ with XX being 1 or 2 and ZZZZ being 2 or 4 digits
# - MONTH ZZZZ, with ZZZZ being 4 digits
# - MONTH XX, ZZZZ with XX being 1 or 2 and ZZZZ being 4 digits
from documents.loggers import LoggingMixin
from documents.signals import document_consumer_declaration

# TODO: isnt there a date parsing library for this?

DATE_REGEX = re.compile(
    r'(\b|(?!=([_-])))([0-9]{1,2})[\.\/-]([0-9]{1,2})[\.\/-]([0-9]{4}|[0-9]{2})(\b|(?=([_-])))|'   # NOQA: E501
    r'(\b|(?!=([_-])))([0-9]{4}|[0-9]{2})[\.\/-]([0-9]{1,2})[\.\/-]([0-9]{1,2})(\b|(?=([_-])))|'   # NOQA: E501
    r'(\b|(?!=([_-])))([0-9]{1,2}[\. ]+[^ ]{3,9} ([0-9]{4}|[0-9]{2}))(\b|(?=([_-])))|'   # NOQA: E501
    r'(\b|(?!=([_-])))([^\W\d_]{3,9} [0-9]{1,2}, ([0-9]{4}))(\b|(?=([_-])))|'
    r'(\b|(?!=([_-])))([^\W\d_]{3,9} [0-9]{4})(\b|(?=([_-])))'
)


logger = logging.getLogger(__name__)


def is_mime_type_supported(mime_type):
    return get_parser_class_for_mime_type(mime_type) is not None


def get_default_file_extension(mime_type):
    for response in document_consumer_declaration.send(None):
        parser_declaration = response[1]
        supported_mime_types = parser_declaration["mime_types"]

        if mime_type in supported_mime_types:
            return supported_mime_types[mime_type]

    return None


def is_file_ext_supported(ext):
    if ext:
        return ext.lower() in get_supported_file_extensions()
    else:
        return False


def get_supported_file_extensions():
    extensions = set()
    for response in document_consumer_declaration.send(None):
        parser_declaration = response[1]
        supported_mime_types = parser_declaration["mime_types"]

        for mime_type in supported_mime_types:
            extensions.update(mimetypes.guess_all_extensions(mime_type))

    return extensions


def get_parser_class_for_mime_type(mime_type):

    options = []

    # Sein letzter Befehl war: KOMMT! Und sie kamen. Alle. Sogar die Parser.

    for response in document_consumer_declaration.send(None):
        parser_declaration = response[1]
        supported_mime_types = parser_declaration["mime_types"]

        if mime_type in supported_mime_types:
            options.append(parser_declaration)

    if not options:
        return None

    # Return the parser with the highest weight.
    return sorted(
        options, key=lambda _: _["weight"], reverse=True)[0]["parser"]


def get_parser_class(path):
    """
    Determine the appropriate parser class based on the file
    """

    mime_type = magic.from_file(path, mime=True)

    return get_parser_class_for_mime_type(mime_type)


def run_convert(input_file,
                output_file,
                density=None,
                scale=None,
                alpha=None,
                strip=False,
                trim=False,
                type=None,
                depth=None,
                extra=None,
                logging_group=None):

    environment = os.environ.copy()
    if settings.CONVERT_MEMORY_LIMIT:
        environment["MAGICK_MEMORY_LIMIT"] = settings.CONVERT_MEMORY_LIMIT
    if settings.CONVERT_TMPDIR:
        environment["MAGICK_TMPDIR"] = settings.CONVERT_TMPDIR

    args = [settings.CONVERT_BINARY]
    args += ['-density', str(density)] if density else []
    args += ['-scale', str(scale)] if scale else []
    args += ['-alpha', str(alpha)] if alpha else []
    args += ['-strip'] if strip else []
    args += ['-trim'] if trim else []
    args += ['-type', str(type)] if type else []
    args += ['-depth', str(depth)] if depth else []
    args += [input_file, output_file]

    logger.debug("Execute: " + " ".join(args), extra={'group': logging_group})

    if not subprocess.Popen(args, env=environment).wait() == 0:
        raise ParseError("Convert failed at {}".format(args))


def parse_date(filename, text):
    """
    Returns the date of the document.
    """

    def __parser(ds, date_order):
        """
        Call dateparser.parse with a particular date ordering
        """
        return dateparser.parse(
            ds,
            settings={
                "DATE_ORDER": date_order,
                "PREFER_DAY_OF_MONTH": "first",
                "RETURN_AS_TIMEZONE_AWARE":
                True
            }
        )

    date = None

    next_year = timezone.now().year + 5  # Arbitrary 5 year future limit

    # if filename date parsing is enabled, search there first:
    if settings.FILENAME_DATE_ORDER:
        for m in re.finditer(DATE_REGEX, filename):
            date_string = m.group(0)

            try:
                date = __parser(date_string, settings.FILENAME_DATE_ORDER)
            except (TypeError, ValueError):
                # Skip all matches that do not parse to a proper date
                continue

            if date is not None and next_year > date.year > 1900:
                return date

    # Iterate through all regex matches in text and try to parse the date
    for m in re.finditer(DATE_REGEX, text):
        date_string = m.group(0)

        try:
            date = __parser(date_string, settings.DATE_ORDER)
        except (TypeError, ValueError):
            # Skip all matches that do not parse to a proper date
            continue

        if date is not None and next_year > date.year > 1900:
            break
        else:
            date = None

    return date


class ParseError(Exception):
    pass


class DocumentParser(LoggingMixin):
    """
    Subclass this to make your own parser.  Have a look at
    `paperless_tesseract.parsers` for inspiration.
    """

    def __init__(self, logging_group):
        super().__init__()
        self.logging_group = logging_group
        self.tempdir = tempfile.mkdtemp(
            prefix="paperless-", dir=settings.SCRATCH_DIR)

        self.archive_path = None
        self.text = None
        self.date = None

    def parse(self, document_path, mime_type):
        raise NotImplementedError()

    def get_archive_path(self):
        return self.archive_path

    def get_thumbnail(self, document_path, mime_type):
        """
        Returns the path to a file we can use as a thumbnail for this document.
        """
        raise NotImplementedError()

    def get_optimised_thumbnail(self, document_path, mime_type):
        thumbnail = self.get_thumbnail(document_path, mime_type)
        if settings.OPTIMIZE_THUMBNAILS:
            out_path = os.path.join(self.tempdir, "thumb_optipng.png")

            args = (settings.OPTIPNG_BINARY,
                    "-silent", "-o5", thumbnail, "-out", out_path)

            self.log('debug', f"Execute: {' '.join(args)}")

            if not subprocess.Popen(args).wait() == 0:
                raise ParseError("Optipng failed at {}".format(args))

            return out_path
        else:
            return thumbnail

    def get_text(self):
        return self.text

    def get_date(self):
        return self.date

    def cleanup(self):
        self.log("debug", "Deleting directory {}".format(self.tempdir))
        shutil.rmtree(self.tempdir)
