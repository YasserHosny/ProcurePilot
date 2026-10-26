import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { I18nService } from '../../../core/i18n/i18n.service';
import { BrandLogoComponent } from '../../../layout/brand-logo/brand-logo.component';
import { LanguageToggleComponent } from '../../../layout/language-toggle/language-toggle.component';

export interface LegalSection {
  readonly id: string;
  readonly heading: string;
  readonly paragraphs: readonly string[];
}

export interface LegalDoc {
  readonly title: string;
  readonly intro: string;
  readonly sections: readonly LegalSection[];
}

export function parseLegalDoc(raw: unknown): LegalDoc {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return { title: '', intro: '', sections: [] };
  }
  const record = raw as Record<string, unknown>;
  const title = typeof record['title'] === 'string' ? record['title'] : '';
  const intro = typeof record['intro'] === 'string' ? record['intro'] : '';
  const rawSections = record['sections'];

  if (!rawSections || typeof rawSections !== 'object' || Array.isArray(rawSections)) {
    return { title, intro, sections: [] };
  }

  const sectionsRecord = rawSections as Record<string, unknown>;
  const sectionKeys = Object.keys(sectionsRecord).sort();
  const sections: LegalSection[] = [];

  for (const sKey of sectionKeys) {
    const sec = sectionsRecord[sKey];
    if (!sec || typeof sec !== 'object' || Array.isArray(sec)) continue;
    const secRecord = sec as Record<string, unknown>;
    const heading = typeof secRecord['heading'] === 'string' ? secRecord['heading'] : '';

    const pKeys = Object.keys(secRecord)
      .filter((k) => /^p\d+$/.test(k))
      .sort((a, b) => parseInt(a.slice(1), 10) - parseInt(b.slice(1), 10));

    const paragraphs: string[] = [];
    for (const pKey of pKeys) {
      const val = secRecord[pKey];
      if (typeof val === 'string' && val.length > 0) {
        paragraphs.push(val);
      }
    }

    sections.push({ id: sKey, heading, paragraphs });
  }

  return { title, intro, sections };
}

@Component({
  selector: 'app-legal-page',
  standalone: true,
  imports: [
    BrandLogoComponent,
    LanguageToggleComponent,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    TranslatePipe,
  ],
  templateUrl: './legal-page.component.html',
  styleUrl: './legal-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LegalPageComponent {
  private readonly translate = inject(TranslateService);
  readonly i18n = inject(I18nService);

  readonly docKey = input.required<'privacy' | 'terms'>();
  readonly isRtl = this.i18n.isRtl;

  private readonly langChangeCounter = signal(0);

  constructor() {
    this.translate.onLangChange.pipe(takeUntilDestroyed()).subscribe(() => {
      this.langChangeCounter.update((n) => n + 1);
    });
    this.translate.onTranslationChange.pipe(takeUntilDestroyed()).subscribe(() => {
      this.langChangeCounter.update((n) => n + 1);
    });
  }

  readonly doc = computed<LegalDoc>(() => {
    this.i18n.currentLocale();
    this.langChangeCounter();
    const key = this.docKey() === 'privacy' ? 'legal.privacy' : 'legal.terms';
    const raw = this.translate.instant(key);
    return parseLegalDoc(raw);
  });
}
