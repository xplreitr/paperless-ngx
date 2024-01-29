import { ComponentFixture, TestBed } from '@angular/core/testing'

import { PageChooserComponent } from './page-chooser.component'
import { NgbActiveModal } from '@ng-bootstrap/ng-bootstrap'
import { HttpClientTestingModule } from '@angular/common/http/testing'
import { PdfViewerComponent } from '../pdf-viewer/pdf-viewer.component'

describe('PageChooserComponent', () => {
  let component: PageChooserComponent
  let fixture: ComponentFixture<PageChooserComponent>

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [PageChooserComponent, PdfViewerComponent],
      providers: [NgbActiveModal],
      imports: [HttpClientTestingModule],
    }).compileComponents()
  })

  beforeEach(() => {
    fixture = TestBed.createComponent(PageChooserComponent)
    component = fixture.componentInstance
    component.document = {
      id: 1,
      title: 'test',
    }
    fixture.detectChanges()
  })

  it('should toggle the "disabled" class if splitting is enabled and page is not in enabledPages', () => {
    const pageRenderedEvent = {
      source: {
        div: document.createElement('div'),
      },
    }
    const div = pageRenderedEvent.source.div as HTMLDivElement
    div.dataset.pageNumber = '1'
    component.splitting = true
    component.enabledPages = [2, 3]

    component.afterPageRendered(pageRenderedEvent)

    expect(div.classList.contains('disabled')).toBe(true)
  })

  it('should toggle the "selected" class if splitting is disabled and page is in pages', () => {
    const pageRenderedEvent = {
      source: {
        div: document.createElement('div'),
      },
    }
    const div = pageRenderedEvent.source.div as HTMLDivElement
    div.dataset.pageNumber = '1'
    component.splitting = false
    component.pages = [1, 2, 3]

    component.afterPageRendered(pageRenderedEvent)

    expect(div.classList.contains('selected')).toBe(true)
  })
})
