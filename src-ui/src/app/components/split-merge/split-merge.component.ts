import { Component, OnInit, OnDestroy } from '@angular/core'
import { Router } from '@angular/router'
import { SplitMergeMetadata } from 'src/app/data/split-merge-request'
import { SplitMergeService } from 'src/app/services/split-merge.service'
import { DocumentService } from 'src/app/services/rest/document.service'
import { DocumentListViewService } from 'src/app/services/document-list-view.service'
import { Subject, Subscription } from 'rxjs'
import { debounceTime } from 'rxjs/operators'
import { NgbModal } from '@ng-bootstrap/ng-bootstrap'
import { PageChooserComponent } from 'src/app/components/common/page-chooser/page-chooser.component'
import { Document, DocumentPart } from 'src/app/data/document'
import {
  CdkDragDrop,
  CdkDragEnd,
  CdkDragStart,
  moveItemInArray,
} from '@angular/cdk/drag-drop'
import { PDFDocumentProxy } from '../common/pdf-viewer/typings'
import { SettingsService } from 'src/app/services/settings.service'

@Component({
  selector: 'pngx-split-merge',
  templateUrl: './split-merge.component.html',
  styleUrls: ['./split-merge.component.scss'],
})
export class SplitMergeComponent implements OnInit, OnDestroy {
  public loading: boolean = false

  public previewUrls: string[] = []
  public previewNumPages: number[] = []
  public previewCurrentPages: number[] = []

  public delete_source_documents: boolean = false

  public metadata_setting: SplitMergeMetadata = SplitMergeMetadata.COPY_FIRST

  private previewDebounce$ = new Subject()

  private previewSub: Subscription

  public error: string

  constructor(
    public splitMergeService: SplitMergeService,
    private documentService: DocumentService,
    private list: DocumentListViewService,
    private settingsService: SettingsService,
    private router: Router,
    private modalService: NgbModal
  ) {}

  ngOnInit() {
    this.previewSub = this.previewDebounce$
      .pipe(debounceTime(400))
      .subscribe(() => {
        if (this.splitMergeService.hasDocuments()) {
          this.save(true)
        } else {
          this.previewUrls = []
          this.error = undefined
        }
      })
    this.previewDebounce$.next(null)
  }

  ngOnDestroy() {
    this.previewDebounce$.complete()
  }

  get documents(): Array<DocumentPart> {
    return this.splitMergeService.getDocuments()
  }

  getThumbUrl(documentId: number) {
    return this.documentService.getThumbUrl(documentId)
  }

  get splitMergeMetadata() {
    return SplitMergeMetadata
  }

  chooseDocuments() {
    this.router.navigate(['documents'])
  }

  onDragStart(event: CdkDragStart) {
    this.settingsService.globalDropzoneEnabled = false
  }

  onDragEnd(event: CdkDragEnd) {
    this.settingsService.globalDropzoneEnabled = true
  }

  onDrop(event: CdkDragDrop<Document[]>) {
    if (event.previousIndex == event.currentIndex) return

    moveItemInArray(this.documents, event.previousIndex, event.currentIndex)
    this.previewDebounce$.next(null)
  }

  cancel() {
    this.splitMergeService.clear()
    this.router.navigate([''])
  }

  save(preview: boolean = false) {
    this.loading = true
    this.previewUrls = []
    this.splitMergeService
      .executeSplitMerge(
        preview,
        this.delete_source_documents,
        this.metadata_setting
      )
      .subscribe(
        (result) => {
          this.loading = false
          this.error = undefined
          if (preview) {
            this.previewUrls = result.map((r) =>
              this.splitMergeService.getPreviewUrl(r)
            )
          } else {
            this.splitMergeService.clear()
            this.router.navigate([''])
          }
        },
        (error) => {
          this.error = error
          this.loading = false
        }
      )
  }

  removeDocument(d: Document, index: number) {
    this.splitMergeService.removeDocument(d, index)
    this.previewNumPages[index] = this.previewCurrentPages[index] = undefined
    this.previewDebounce$.next(null)
  }

  choosePages(d: Document, index: number) {
    let modal = this.modalService.open(PageChooserComponent, {
      backdrop: 'static',
      size: 'lg',
    })
    modal.componentInstance.document = d
    modal.componentInstance.confirmPages.subscribe((pages) => {
      this.splitMergeService.setDocumentPages(d, index, pages)
      modal.componentInstance.buttonsEnabled = false
      modal.close()
      this.previewDebounce$.next(null)
    })
  }

  chooseSplit(d: Document, index: number) {
    let modal = this.modalService.open(PageChooserComponent, {
      backdrop: 'static',
      size: 'lg',
    })
    modal.componentInstance.document = d
    const enabledPages = (d as DocumentPart).pages
    modal.componentInstance.splitting = true
    modal.componentInstance.confirmPages.subscribe((pages) => {
      this.splitMergeService.splitDocument(d, index, pages, enabledPages)
      modal.componentInstance.buttonsEnabled = false
      modal.close()
      this.previewDebounce$.next(null)
    })
  }

  pagesFieldChange(pageStr: string, d: Document, index: number) {
    let pages = pageStr.split(',').map((p) => {
      if (p.indexOf('-') !== -1) {
        const minmax = p.split('-')
        let range = []
        for (let i = parseInt(minmax[0]); i <= parseInt(minmax[1]); i++) {
          range.push(i)
        }
        return range
      } else if (p.length > 0) {
        return parseInt(p)
      } else {
        return null
      }
    })
    pages = [].concat.apply([], pages) // e.g. flat()
    pages = pages.filter((page) => page !== null)
    this.splitMergeService.setDocumentPages(d, index, pages as number[])
    this.previewDebounce$.next(null)
  }

  formatPages(pages: number[]): string {
    let pageStrings = []
    let rangeStart, rangeEnd

    pages?.forEach((page) => {
      if (rangeStart == undefined) {
        rangeStart = page
      } else if (page - rangeStart == 1) {
        rangeEnd = page
      } else if (rangeEnd !== undefined && page - rangeEnd == 1) {
        rangeEnd = page
      } else {
        pageStrings.push(
          rangeEnd !== undefined ? rangeStart + '-' + rangeEnd : rangeStart
        )
        rangeStart = page
        rangeEnd = undefined
      }
    })

    if (rangeEnd !== undefined) {
      pageStrings.push(rangeStart + '-' + rangeEnd)
    } else if (rangeStart !== undefined) {
      pageStrings.push(rangeStart)
    }
    return pageStrings.join(',')
  }

  pdfPreviewLoaded(pdf: PDFDocumentProxy, index: number) {
    this.previewNumPages[index] = pdf.numPages
  }

  pdfPageRendered(event: any, index) {
    console.log(event)

    // CustomEvent is es6
    if (event.pageNumber > 0 && this.previewCurrentPages[index] == undefined)
      this.previewCurrentPages[index] = 1
  }
}
