import { initErrorReporting } from './app/core/observability/sentry';
import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { AppComponent } from './app/app.component';

initErrorReporting();

bootstrapApplication(AppComponent, appConfig)
  .catch((err) => console.error(err));
