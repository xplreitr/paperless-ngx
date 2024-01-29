import { TestBed } from '@angular/core/testing'

import { SplitMergeService } from './split-merge.service'
import {
  HttpClientTestingModule,
  HttpTestingController,
} from '@angular/common/http/testing'

describe('SplitMergeService', () => {
  let service: SplitMergeService
  let httpTestingController: HttpTestingController

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [SplitMergeService],
      imports: [HttpClientTestingModule],
    })

    service = TestBed.inject(SplitMergeService)
    httpTestingController = TestBed.inject(HttpTestingController)
  })

  it('should be created', () => {
    expect(service).toBeTruthy()
  })
})
