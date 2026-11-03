import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Title } from '@angular/platform-browser';
import { provideRouter, Router, TitleStrategy } from '@angular/router';
import { MissingTranslationHandler, provideTranslateService, TranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import { AppMissingTranslationHandler } from '../i18n/missing-translation.handler';
import { TranslatedTitleStrategy } from './translated-title.strategy';

@Component({ selector: 'app-title-test-page', template: '' })
class TitleTestPageComponent {}

describe('TranslatedTitleStrategy', () => {
  let router: Router;
  let title: Title;
  let translate: TranslateService;
  let originalTitle: string;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'history', component: TitleTestPageComponent, title: 'rfq.pageTitle.history' },
          { path: 'create', component: TitleTestPageComponent, title: 'rfq.pageTitle.create' },
          { path: 'untitled', component: TitleTestPageComponent },
          { path: 'unknown', component: TitleTestPageComponent, title: 'rfq.pageTitle.unknown' },
        ]),
        provideTranslateService({ missingTranslationHandler: {
          provide: MissingTranslationHandler, useClass: AppMissingTranslationHandler,
        } }),
        { provide: TitleStrategy, useClass: TranslatedTitleStrategy },
      ],
    });
    router = TestBed.inject(Router);
    title = TestBed.inject(Title);
    originalTitle = title.getTitle();
    translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', { rfq: { pageTitle: { history: 'RFQ History', create: 'Create RFQ' } } });
    translate.setTranslation('ar', { rfq: { pageTitle: { history: 'سجل طلبات عروض الأسعار', create: 'إنشاء طلب عرض أسعار' } } });
    translate.use('en');
  });

  afterEach(() => title.setTitle(originalTitle));

  it('sets the translated route title with the app name', async () => {
    await router.navigateByUrl('/history');
    expect(title.getTitle()).toBe('RFQ History · ProcurePilot');
  });

  it('updates the current route title when the language switches', async () => {
    await router.navigateByUrl('/history');
    translate.use('ar');
    expect(title.getTitle()).toBe('سجل طلبات عروض الأسعار · ProcurePilot');
  });

  it('falls back to the app name for a route without a title', async () => {
    await router.navigateByUrl('/history');
    await router.navigateByUrl('/untitled');
    translate.use('ar');
    expect(title.getTitle()).toBe('ProcurePilot');
  });

  it('falls back for an unknown key with the app missing-key handler', async () => {
    spyOn(console, 'error');
    await router.navigateByUrl('/unknown');
    expect(title.getTitle()).toBe('ProcurePilot');
  });

  it('never displays a raw unknown key', async () => {
    spyOn(translate, 'stream').and.returnValue(of('rfq.pageTitle.unknown'));
    await router.navigateByUrl('/unknown');
    expect(title.getTitle()).toBe('ProcurePilot');
  });

  it('uses only the latest route on subsequent language switches', async () => {
    await router.navigateByUrl('/history');
    await router.navigateByUrl('/create');
    translate.use('ar');
    expect(title.getTitle()).toBe('إنشاء طلب عرض أسعار · ProcurePilot');
  });
});
