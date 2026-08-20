import { TestBed } from '@angular/core/testing';
import { DOCUMENT } from '@angular/common';
import { Directionality } from '@angular/cdk/bidi';

import { DirectionService } from './direction.service';

describe('DirectionService (T064)', () => {
  let service: DirectionService;
  let doc: Document;
  let cdkDir: Directionality;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [DirectionService, Directionality],
    });
    service = TestBed.inject(DirectionService);
    doc = TestBed.inject(DOCUMENT);
    cdkDir = TestBed.inject(Directionality);
  });

  it('should default to ltr', () => {
    expect(service.currentDirection()).toBe('ltr');
    expect(service.isRtl()).toBeFalse();
  });

  it('should switch to rtl and update document and CDK Directionality', () => {
    service.setDirection('rtl', 'ar');

    expect(service.currentDirection()).toBe('rtl');
    expect(service.isRtl()).toBeTrue();
    expect(doc.documentElement.getAttribute('dir')).toBe('rtl');
    expect(doc.documentElement.getAttribute('lang')).toBe('ar');
    expect(cdkDir.value).toBe('rtl');
  });

  it('should switch back to ltr and update document and CDK Directionality', () => {
    service.setDirection('rtl', 'ar');
    service.setDirection('ltr', 'en');

    expect(service.currentDirection()).toBe('ltr');
    expect(service.isRtl()).toBeFalse();
    expect(doc.documentElement.getAttribute('dir')).toBe('ltr');
    expect(doc.documentElement.getAttribute('lang')).toBe('en');
    expect(cdkDir.value).toBe('ltr');
  });
});
