import { ComponentFixture, TestBed } from '@angular/core/testing'

import { SplitMergeComponent } from './split-merge.component'
import { HttpClientTestingModule } from '@angular/common/http/testing'
import { NgxBootstrapIconsModule, allIcons } from 'ngx-bootstrap-icons'
import { PageHeaderComponent } from '../common/page-header/page-header.component'
import { NgbPopoverModule } from '@ng-bootstrap/ng-bootstrap'

describe('SplitMergeComponent', () => {
  let component: SplitMergeComponent
  let fixture: ComponentFixture<SplitMergeComponent>

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [SplitMergeComponent, PageHeaderComponent],
      imports: [
        HttpClientTestingModule,
        NgxBootstrapIconsModule.pick(allIcons),
        NgbPopoverModule,
      ],
    }).compileComponents()
  })

  beforeEach(() => {
    fixture = TestBed.createComponent(SplitMergeComponent)
    component = fixture.componentInstance
    fixture.detectChanges()
  })

  it('should create', () => {
    expect(component).toBeTruthy()
  })
})
