import { TestBed } from '@angular/core/testing';
import { PredictionComponent } from './prediction/prediction.component';


describe('AppComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ PredictionComponent],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent( PredictionComponent);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it(`should have the 'demand-predictor-frontend' title`, () => {
    const fixture = TestBed.createComponent( PredictionComponent);
    const app = fixture.componentInstance;
    expect(app.title).toEqual('demand-predictor-frontend');
  });

  it('should render title', () => {
    const fixture = TestBed.createComponent( PredictionComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('h1')?.textContent).toContain('Hello, demand-predictor-frontend');
  });
});
