import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { PredictionComponent } from './app/prediction/prediction.component';

bootstrapApplication(PredictionComponent, appConfig)
  .catch((err) => console.error(err));