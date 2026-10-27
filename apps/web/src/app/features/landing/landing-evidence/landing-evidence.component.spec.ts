import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import arCatalog from '../../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../../packages/i18n/en.json';
import { I18nService } from '../../../core/i18n/i18n.service';
import { LandingEvidenceComponent } from './landing-evidence.component';

describe('LandingEvidenceComponent', () => {
  let component: LandingEvidenceComponent;
  let fixture: ComponentFixture<LandingEvidenceComponent>;
  let translate: TranslateService;

  beforeEach(async () => {
    localStorage.clear();

    await TestBed.configureTestingModule({
      imports: [LandingEvidenceComponent],
      providers: [provideTranslateService()],
    }).compileComponents();

    translate = TestBed.inject(TranslateService);
    TestBed.inject(I18nService);
    translate.setTranslation('en', enCatalog);
    translate.setTranslation('ar', arCatalog);
    translate.use('en');

    fixture = TestBed.createComponent(LandingEvidenceComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('creates the component', () => {
    expect(component).toBeTruthy();
  });

  it('evidence excerpt shows the four rows with the verified row marked', () => {
    const excerptRows = fixture.debugElement.queryAll(By.css('.excerpt-row'));
    expect(excerptRows.length).toBe(4);

    const verifiedRow = fixture.debugElement.query(By.css('.excerpt-row.verified-row'));
    expect(verifiedRow).toBeTruthy();

    const verifiedChip = verifiedRow.query(By.css('.excerpt-chip.verified'));
    expect(verifiedChip).toBeTruthy();
    expect(verifiedChip.nativeElement.textContent.trim()).toBe('Verified');
    expect(verifiedRow.nativeElement.textContent).toContain('560');
  });
});
