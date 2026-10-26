import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Component, signal } from '@angular/core';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import arCatalog from '../../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import { I18nService } from '../../../core/i18n/i18n.service';
import { LegalPageComponent } from './legal-page.component';

@Component({
  standalone: true,
  imports: [LegalPageComponent],
  template: `<app-legal-page [docKey]="docKey()" />`,
})
class TestHostComponent {
  readonly docKey = signal<'privacy' | 'terms'>('privacy');
}

describe('LegalPageComponent', () => {
  let hostComponent: TestHostComponent;
  let fixture: ComponentFixture<TestHostComponent>;
  let translate: TranslateService;

  beforeEach(async () => {
    localStorage.clear();

    await TestBed.configureTestingModule({
      imports: [TestHostComponent],
      providers: [
        provideRouter([]),
        provideTranslateService(),
      ],
    }).compileComponents();

    translate = TestBed.inject(TranslateService);
    TestBed.inject(I18nService);
    translate.setTranslation('en', enCatalog);
    translate.setTranslation('ar', arCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(TestHostComponent);
    hostComponent = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('renders privacy document with 10 sections and switches to terms with 11 sections', () => {
    let title = fixture.debugElement.query(By.css('.legal-title'));
    expect(title.nativeElement.textContent.trim()).toBe('Privacy Policy');

    let sections = fixture.debugElement.queryAll(By.css('.legal-section'));
    expect(sections.length).toBe(10);

    hostComponent.docKey.set('terms');
    fixture.detectChanges();

    title = fixture.debugElement.query(By.css('.legal-title'));
    expect(title.nativeElement.textContent.trim()).toBe('Terms of Service');

    sections = fixture.debugElement.queryAll(By.css('.legal-section'));
    expect(sections.length).toBe(11);
  });
});
