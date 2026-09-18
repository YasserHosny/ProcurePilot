import { NgClass } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { RoleDirective } from '../../../core/auth/role.directive';
import { FormatDatePipe } from '../../../core/format/date.pipe';
import {
  PosApiService,
  type PosConnection,
} from '../pos-api';

@Component({
  selector: 'app-connection-settings',
  standalone: true,
  imports: [
    NgClass,
    MatButtonModule,
    MatCardModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    TranslatePipe,
    FormatDatePipe,
    RoleDirective,
  ],
  templateUrl: './connection-settings.component.html',
  styleUrl: './connection-settings.component.scss',
})
export class ConnectionSettingsComponent implements OnInit {
  private readonly posApi = inject(PosApiService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly translate = inject(TranslateService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  readonly isLoading = signal<boolean>(true);
  readonly isMutating = signal<boolean>(false);
  readonly connection = signal<PosConnection | null>(null);
  readonly error = signal<string | null>(null);

  ngOnInit(): void {
    this.handleOAuthCallbackParams();
    this.loadConnection();
  }

  loadConnection(): void {
    this.isLoading.set(true);
    this.error.set(null);

    this.posApi.getConnection().subscribe({
      next: (conn) => {
        this.isLoading.set(false);
        this.connection.set(conn);
      },
      error: (err: unknown) => {
        this.isLoading.set(false);
        if (err instanceof HttpErrorResponse && err.status === 404) {
          this.connection.set(null);
        } else {
          this.error.set(this.translate.instant('pos.connection.loadError'));
        }
      },
    });
  }

  connect(): void {
    if (this.isMutating()) {
      return;
    }
    this.isMutating.set(true);

    this.posApi.connect().subscribe({
      next: (response) => {
        this.isMutating.set(false);
        this.redirectToUrl(response.authorization_url);
      },
      error: () => {
        this.isMutating.set(false);
        this.snackBar.open(
          this.translate.instant('pos.connection.startFailed'),
          undefined,
          { duration: 4000 },
        );
      },
    });
  }

  disconnect(): void {
    if (this.isMutating()) {
      return;
    }
    this.isMutating.set(true);

    this.posApi.disconnect().subscribe({
      next: (updatedConnection) => {
        this.isMutating.set(false);
        this.connection.set(updatedConnection);
        this.snackBar.open(
          this.translate.instant('pos.connection.disconnectSuccess'),
          undefined,
          { duration: 3000 },
        );
      },
      error: () => {
        this.isMutating.set(false);
        this.snackBar.open(
          this.translate.instant('pos.connection.disconnectFailed'),
          undefined,
          { duration: 4000 },
        );
      },
    });
  }

  redirectToUrl(url: string): void {
    window.location.href = url;
  }

  private handleOAuthCallbackParams(): void {
    const status = this.route.snapshot?.queryParamMap?.get('pos_connected');
    if (status === 'success') {
      this.snackBar.open(
        this.translate.instant('pos.connection.connectedSuccess'),
        undefined,
        { duration: 3000 },
      );
      this.clearCallbackQueryParam();
    } else if (status === 'failed') {
      this.snackBar.open(
        this.translate.instant('pos.connection.connectFailed'),
        undefined,
        { duration: 4000 },
      );
      this.clearCallbackQueryParam();
    }
  }

  private clearCallbackQueryParam(): void {
    void this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { pos_connected: null },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
}
