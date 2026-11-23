import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';

import arCatalog from '../../../../../../packages/i18n/ar.json';
import enCatalog from '../../../../../../packages/i18n/en.json';
import { CursorPager } from './cursor-pager';
import { ListPagerComponent } from './list-pager.component';

@Component({
  standalone: true,
  imports: [ListPagerComponent],
  template: `<app-list-pager [pager]="pager" label="Spec pages" [busy]="busy" (pageChange)="changes = changes + 1" />`,
})
class HostComponent {
  readonly pager = new CursorPager('pager-spec');
  busy = false;
  changes = 0;
}

describe('ListPagerComponent', () => {
  let fixture: ComponentFixture<HostComponent>;
  let host: HostComponent;
  let translate: TranslateService;

  const el = (selector: string) => (fixture.nativeElement as HTMLElement).querySelector(selector) as HTMLElement;
  const range = () => el('.list-pager__range').textContent?.trim();

  beforeEach(async () => {
    localStorage.removeItem('pp.pageSize.pager-spec');
    await TestBed.configureTestingModule({
      imports: [HostComponent],
      providers: [provideTranslateService(), provideNoopAnimations()],
    }).compileComponents();
    translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', enCatalog);
    translate.setTranslation('ar', arCatalog);
    translate.use('en');
    fixture = TestBed.createComponent(HostComponent);
    host = fixture.componentInstance;
    host.pager.loaded({ items: Array.from({ length: 25 }), next_cursor: 'c2', total: 34 });
    fixture.detectChanges();
  });

  it('is a labelled navigation landmark with the range, the total and a polite status', () => {
    expect(el('nav').getAttribute('aria-label')).toBe('Spec pages');
    expect(range()).toBe('1–25 of 34');
    expect(el('.list-pager__range').getAttribute('aria-live')).toBe('polite');
    expect(el('mat-label').textContent?.trim()).toBe('Rows per page');
  });

  it('Next and Previous move the pager and ask the host to reload', () => {
    const previous = el('.list-pager__previous') as HTMLButtonElement;
    const next = el('.list-pager__next') as HTMLButtonElement;
    expect(previous.disabled).toBeTrue();

    next.click();
    expect(host.changes).toBe(1);
    expect(host.pager.params()).toEqual({ cursor: 'c2', limit: 25 });

    host.pager.loaded({ items: Array.from({ length: 9 }), next_cursor: null, total: 34 });
    fixture.detectChanges();
    expect(range()).toBe('26–34 of 34');
    expect(next.disabled).toBeTrue();

    previous.click();
    expect(host.changes).toBe(2);
    expect(host.pager.params()).toEqual({ limit: 25 });
  });

  it('shows the open range when the list cannot count', () => {
    host.pager.loaded({ items: Array.from({ length: 25 }), next_cursor: 'c2' });
    fixture.detectChanges();
    expect(range()).toBe('1–25');
  });

  it('disables every control and shows Loading in place of the range while a page loads', () => {
    host.busy = true;
    fixture.detectChanges();
    expect(range()).toBe('Loading...');
    expect((el('.list-pager__next') as HTMLButtonElement).disabled).toBeTrue();
    expect(el('mat-select').getAttribute('aria-disabled')).toBe('true');
  });

  it('a page-size choice reloads from the first page', () => {
    const pager = fixture.debugElement.children[0].componentInstance as ListPagerComponent;
    pager.onPageSize(10);
    expect(host.changes).toBe(1);
    expect(host.pager.params()).toEqual({ limit: 10 });
    pager.onPageSize(10);
    expect(host.changes).toBe(1);
  });

  it('renders the Arabic copy with Arabic-Indic digits', () => {
    translate.use('ar');
    fixture.detectChanges();
    expect(range()).toBe('١–٢٥ من ٣٤');
    expect(el('.list-pager__next').textContent).toContain('التالي');
  });
});
