import { Injectable, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Title } from '@angular/platform-browser';
import { RouterStateSnapshot, TitleStrategy } from '@angular/router';
import { TranslateService } from '@ngx-translate/core';
import { BehaviorSubject, of, switchMap } from 'rxjs';

const APP_NAME = 'ProcurePilot';

@Injectable()
export class TranslatedTitleStrategy extends TitleStrategy {
  private readonly title = inject(Title);
  private readonly translate = inject(TranslateService);
  private readonly titleKey = new BehaviorSubject<string | undefined>(undefined);

  constructor() {
    super();
    this.titleKey.pipe(
      switchMap((key) => key ? this.translate.stream(key) : of(undefined)),
      takeUntilDestroyed(),
    ).subscribe((translated) => {
      const key = this.titleKey.value;
      // The app's development handler returns a marker; ngx-translate's default
      // and the production handler return the raw key when a translation is missing.
      const text = typeof translated === 'string' ? translated.trim() : '';
      const hasTitle = text && text !== key && text !== `[MISSING: ${key}]`;
      this.title.setTitle(hasTitle ? `${text} · ${APP_NAME}` : APP_NAME);
    });
  }

  override updateTitle(snapshot: RouterStateSnapshot): void {
    this.titleKey.next(this.buildTitle(snapshot));
  }
}
