import {
  ComponentFixture,
  TestBed,
  fakeAsync,
  tick,
} from '@angular/core/testing'

import { InputDebounceComponent } from './input-debounce.component'
import { FormsModule, ReactiveFormsModule } from '@angular/forms'

describe('InputDebounceComponent', () => {
  let component: InputDebounceComponent
  let fixture: ComponentFixture<InputDebounceComponent>

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [InputDebounceComponent],
      imports: [FormsModule, ReactiveFormsModule],
    }).compileComponents()
  })

  beforeEach(() => {
    fixture = TestBed.createComponent(InputDebounceComponent)
    component = fixture.componentInstance
    fixture.detectChanges()
  })

  it('should emit input value on keyup event', fakeAsync(() => {
    const inputValue = 'Test Input'
    component.inputValue = inputValue
    const inputElement = fixture.nativeElement
    const valueSpy = jest.spyOn(component.value, 'emit')

    inputElement.dispatchEvent(new Event('keyup'))
    tick(500)

    expect(valueSpy).toHaveBeenCalledWith(inputValue)
  }))

  it('should prevent input of invalid characters', () => {
    component.keyUp(null) // coverage
    component.inputValue = ''
    component.pattern = '/[0-9]/'
    const inputElement = fixture.nativeElement.querySelector('input')
    inputElement.dispatchEvent(new KeyboardEvent('keyup', { key: 'a' }))
    expect(component.inputValue).toBe('')
  })

  it('should clear input value', () => {
    component.inputValue = 'Test Input'
    component.clear()
    expect(component.inputValue).toBe('')
  })
})
