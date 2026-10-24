import { Signal, signal, WritableSignal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideTranslateService } from '@ngx-translate/core';
import { of } from 'rxjs';

import type { Locale } from '../../core/api/models';
import { I18nService } from '../../core/i18n/i18n.service';
import { LanguageToggleComponent } from './language-toggle.component';

describe('LanguageToggleComponent', () => {
  let component: LanguageToggleComponent;
  let fixture: ComponentFixture<LanguageToggleComponent>;
  let currentLocaleSignal: WritableSignal<Locale>;
  let i18nSpy: {
    currentLocale: Signal<Locale>;
    setLocale: jasmine.Spy;
  };

  beforeEach(async () => {
    currentLocaleSignal = signal<Locale>('en');
    i18nSpy = {
      currentLocale: currentLocaleSignal.asReadonly(),
      setLocale: jasmine.createSpy('setLocale').and.returnValue(of(null)),
    };

    await TestBed.configureTestingModule({
      imports: [LanguageToggleComponent],
      providers: [
        provideTranslateService(),
        { provide: I18nService, useValue: i18nSpy },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(LanguageToggleComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('creates the component', () => {
    expect(component).toBeTruthy();
  });

  it('shows "عربي" with lang="ar" when English is active, accessible name equals visible label, and title holds hint', () => {
    const button = fixture.debugElement.query(By.css('.lang-toggle-btn'));
    expect(button).toBeTruthy();
    expect(button.nativeElement.getAttribute('aria-label')).toBeNull();
    expect(button.nativeElement.getAttribute('title')).toBe('common.languageToggle.switchToAr');

    const labelSpan = fixture.debugElement.query(By.css('.lang-label'));
    expect(labelSpan).toBeTruthy();
    expect(labelSpan.nativeElement.getAttribute('lang')).toBe('ar');
    expect(labelSpan.nativeElement.textContent.trim()).toBe('common.languageToggle.labelAr');
    expect(button.nativeElement.textContent.trim()).toBe(labelSpan.nativeElement.textContent.trim());

    const obs$ = of(null);
    spyOn(obs$, 'subscribe').and.callThrough();
    i18nSpy.setLocale.and.returnValue(obs$);

    button.nativeElement.click();

    expect(i18nSpy.setLocale).toHaveBeenCalledWith('ar');
    expect(obs$.subscribe).toHaveBeenCalled();
  });

  it('shows "EN" with lang="en" when Arabic is active, accessible name equals visible label, and title holds hint', () => {
    currentLocaleSignal.set('ar');
    fixture.detectChanges();

    const button = fixture.debugElement.query(By.css('.lang-toggle-btn'));
    expect(button).toBeTruthy();
    expect(button.nativeElement.getAttribute('aria-label')).toBeNull();
    expect(button.nativeElement.getAttribute('title')).toBe('common.languageToggle.switchToEn');

    const labelSpan = fixture.debugElement.query(By.css('.lang-label'));
    expect(labelSpan).toBeTruthy();
    expect(labelSpan.nativeElement.getAttribute('lang')).toBe('en');
    expect(labelSpan.nativeElement.textContent.trim()).toBe('common.languageToggle.labelEn');
    expect(button.nativeElement.textContent.trim()).toBe(labelSpan.nativeElement.textContent.trim());

    const obs$ = of(null);
    spyOn(obs$, 'subscribe').and.callThrough();
    i18nSpy.setLocale.and.returnValue(obs$);

    button.nativeElement.click();

    expect(i18nSpy.setLocale).toHaveBeenCalledWith('en');
    expect(obs$.subscribe).toHaveBeenCalled();
  });
});
