import { Clipboard } from '@angular/cdk/clipboard';
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import arCatalog from '../../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import { environment } from '../../../../environments/environment';
import { I18nService } from '../../../core/i18n/i18n.service';
import { LandingPilotComponent } from './landing-pilot.component';

describe('LandingPilotComponent', () => {
  let component: LandingPilotComponent;
  let fixture: ComponentFixture<LandingPilotComponent>;
  let translate: TranslateService;

  beforeEach(async () => {
    localStorage.clear();

    await TestBed.configureTestingModule({
      imports: [LandingPilotComponent],
      providers: [provideTranslateService()],
    }).compileComponents();

    translate = TestBed.inject(TranslateService);
    TestBed.inject(I18nService);
    translate.setTranslation('en', enCatalog);
    translate.setTranslation('ar', arCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(LandingPilotComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('creates the component', () => {
    expect(component).toBeTruthy();
  });

  it('copy-email uses Clipboard and announces "Copied"', fakeAsync(() => {
    const clipboard = TestBed.inject(Clipboard);
    const copySpy = spyOn(clipboard, 'copy').and.returnValue(true);

    const copyBtn = fixture.debugElement.query(By.css('.copy-email-btn'));
    expect(copyBtn).toBeTruthy();

    copyBtn.triggerEventHandler('click', null);
    fixture.detectChanges();

    expect(copySpy).toHaveBeenCalledWith(environment.salesEmail);
    expect(component.emailCopied()).toBeTrue();

    const liveRegion = fixture.debugElement.query(By.css('[aria-live="polite"]'));
    expect(liveRegion.nativeElement.textContent.trim()).toBe('Copied');
    expect(copyBtn.nativeElement.textContent).toContain('Copied');

    tick(2000);
    fixture.detectChanges();
    expect(component.emailCopied()).toBeFalse();
  }));

  it('renders Q&A with 4 items using native details and summary', () => {
    const faqRows = fixture.debugElement.queryAll(By.css('.faq-row'));
    expect(faqRows.length).toBe(4);
    for (const row of faqRows) {
      expect(row.nativeElement.tagName.toLowerCase()).toBe('details');
      const summary = row.query(By.css('summary'));
      expect(summary).toBeTruthy();
      const answer = row.query(By.css('.faq-answer'));
      expect(answer).toBeTruthy();
    }
  });

  it('links WhatsApp to the sales number with a prefilled message', () => {
    const btn = fixture.debugElement.query(By.css('.pilot-whatsapp-btn'));
    expect(btn.nativeElement.getAttribute('href')).toBe(
      `https://wa.me/${environment.salesWhatsapp}?text=${encodeURIComponent(enCatalog.landing.pilot.whatsappMessage)}`,
    );
    expect(btn.nativeElement.getAttribute('target')).toBe('_blank');
    expect(btn.nativeElement.textContent).toContain('Message us on WhatsApp');
    expect(btn.query(By.css('svg.pilot-whatsapp-icon'))).toBeTruthy();
  });

  it('opens a menu of mail options, each carrying the same draft', () => {
    const { emailSubject, emailBody } = enCatalog.landing.pilot;
    const subject = encodeURIComponent(emailSubject);
    const body = encodeURIComponent(emailBody);
    const to = encodeURIComponent(environment.salesEmail);

    fixture.debugElement.query(By.css('.pilot-primary-btn')).nativeElement.click();
    fixture.detectChanges();

    const items = Array.from(document.querySelectorAll<HTMLAnchorElement>('a[mat-menu-item]'));
    expect(items.map((item) => item.getAttribute('href'))).toEqual([
      `https://mail.google.com/mail/?view=cm&fs=1&to=${to}&su=${subject}&body=${body}`,
      `https://outlook.office.com/mail/deeplink/compose?to=${to}&subject=${subject}&body=${body}`,
      `mailto:${environment.salesEmail}?subject=${subject}&body=${body}`,
    ]);
  });
});
