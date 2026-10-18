import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { DateAdapter, MAT_NATIVE_DATE_FORMATS } from '@angular/material/core';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import { SessionService } from '../auth/session.service';
import { AppDateAdapter, provideAppDateAdapter } from './date-adapter';

describe('AppDateAdapter', () => {
  const region = signal<string>('EG');
  const tenant = () => ({ region: region() });
  let adapter: AppDateAdapter;
  let translate: TranslateService;
  const input = MAT_NATIVE_DATE_FORMATS.display.dateInput;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [TranslateModule.forRoot()],
      providers: [provideAppDateAdapter(), { provide: SessionService, useValue: { tenant } }],
    });
    adapter = TestBed.inject(DateAdapter) as AppDateAdapter;
    translate = TestBed.inject(TranslateService);
  });

  it('is day-first in Arabic and for a workspace outside the US region', () => {
    for (const [lang, workspaceRegion] of [['ar', 'US'], ['ar', 'EG'], ['en', 'EG'], ['en', 'GB']]) {
      translate.use(lang);
      region.set(workspaceRegion);
      expect(adapter.format(new Date(2026, 9, 21), input)).withContext(`${lang}/${workspaceRegion}`).toBe('21/10/2026');
      expect(adapter.parse('21/10/2026')?.getMonth()).toBe(9);
    }
  });

  it('is month-first only for an English-language US workspace', () => {
    translate.use('en');
    region.set('US');
    expect(adapter.format(new Date(2026, 9, 21), input)).toBe('10/21/2026');
    expect(adapter.parse('10/21/2026')?.getDate()).toBe(21);
  });

  it('parses Arabic-Indic digits and ISO dates, and rejects impossible dates', () => {
    translate.use('ar');
    region.set('EG');
    const parsed = adapter.parse('٢١/١٠/٢٠٢٦');
    expect([parsed?.getFullYear(), parsed?.getMonth(), parsed?.getDate()]).toEqual([2026, 9, 21]);
    expect(adapter.parse('2026-10-21')?.getDate()).toBe(21);
    expect(adapter.isValid(adapter.parse('31/02/2026') as Date)).toBeFalse();
    expect(adapter.parse('')).toBeNull();
  });

  it('parses typed text without announcing a locale change, and rejects partial dates', () => {
    // Workspace region arrives after the adapter last synced: parsing must still go day-first
    // without emitting localeChanges, which would make Material overwrite the typed text.
    translate.use('en');
    region.set('US');
    adapter.format(new Date(2026, 9, 21), input);
    region.set('GB');
    const seen: number[] = [];
    const sub = adapter.localeChanges.subscribe(() => seen.push(1));
    for (const typed of ['2', '22', '22/1', '22/10/202']) {
      const parsed = adapter.parse(typed);
      expect(parsed && adapter.isValid(parsed)).withContext(typed).toBeFalsy();
    }
    expect(adapter.parse('22/10/2026')?.getDate()).toBe(22);
    expect(seen.length).toBe(0);
    sub.unsubscribe();
  });

  it('names months in the interface language and starts Egyptian weeks on Saturday', () => {
    translate.use('ar');
    expect(adapter.getMonthNames('long')[9]).toBe('أكتوبر');
    expect(adapter.getFirstDayOfWeek()).toBe(6);
    translate.use('en');
    region.set('GB');
    expect(adapter.getMonthNames('long')[9]).toBe('October');
    expect(adapter.getFirstDayOfWeek()).toBe(1);
  });

  it('announces a locale change as soon as the interface language switches', () => {
    translate.use('en');
    region.set('GB');
    adapter.getMonthNames('long');
    const seen: number[] = [];
    const sub = adapter.localeChanges.subscribe(() => seen.push(1));
    translate.use('ar');
    expect(seen.length).toBe(1);
    expect(adapter.getMonthNames('long')[9]).toBe('أكتوبر');
    sub.unsubscribe();
  });
});
