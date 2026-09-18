import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { type WritableSignal, signal } from '@angular/core';
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { By } from '@angular/platform-browser';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import type { Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import type { PosConnection } from '../pos-api';
import { ConnectionSettingsComponent } from './connection-settings.component';

describe('ConnectionSettingsComponent (T014)', () => {
  let component: ConnectionSettingsComponent;
  let fixture: ComponentFixture<ConnectionSettingsComponent>;
  let httpTestingController: HttpTestingController;
  let mockRoleSignal: WritableSignal<Role | null>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let router: Router;
  let mockQueryParamMap: Map<string, string>;

  const mockActiveConnection: PosConnection = {
    id: 'pos-conn-001',
    provider: 'square',
    display_name: 'Acme Square Store',
    status: 'active',
    connected_at: '2026-09-19T08:00:00Z',
    last_synced_at: null,
    disconnected_at: null,
  };

  const mockNeedsReauthConnection: PosConnection = {
    id: 'pos-conn-002',
    provider: 'square',
    display_name: 'Acme Square Sandbox',
    status: 'needs_reauth',
    connected_at: '2026-09-10T10:00:00Z',
    last_synced_at: '2026-09-15T09:30:00Z',
    disconnected_at: null,
  };

  const mockDisconnectedConnection: PosConnection = {
    id: 'pos-conn-003',
    provider: 'square',
    display_name: 'Acme Square Archive',
    status: 'disconnected',
    connected_at: '2026-08-01T08:00:00Z',
    last_synced_at: '2026-08-15T08:00:00Z',
    disconnected_at: '2026-09-01T12:00:00Z',
  };

  beforeEach(async () => {
    mockRoleSignal = signal<Role | null>('owner');
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);
    mockQueryParamMap = new Map<string, string>();

    const mockSessionService = {
      role: mockRoleSignal,
      hasRole: (...roles: readonly Role[]) => {
        const current = mockRoleSignal();
        return current !== null && roles.includes(current);
      },
      isAuthenticated: signal(true),
      activeLocale: signal('en'),
      currentMember: signal(null),
      tenant: signal(null),
    };

    await TestBed.configureTestingModule({
      imports: [ConnectionSettingsComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: SessionService, useValue: mockSessionService },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              queryParamMap: {
                get: (key: string) => mockQueryParamMap.get(key) ?? null,
              },
            },
          },
        },
      ],
    })
      .overrideComponent(ConnectionSettingsComponent, {
        set: {
          providers: [{ provide: MatSnackBar, useValue: snackBarSpy }],
        },
      })
      .compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('en', {
      pos: {
        connection: {
          neverSynced: 'Never synced yet',
          status: {
            active: 'Active',
            needs_reauth: 'Needs Re-authorization',
            disconnected: 'Disconnected',
          },
        },
      },
    });
    translate.use('en');

    router = TestBed.inject(Router);
    spyOn(router, 'navigate').and.returnValue(Promise.resolve(true));

    httpTestingController = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ConnectionSettingsComponent);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    httpTestingController.verify();
  });

  it('should create the component', () => {
    expect(component).toBeTruthy();
  });

  describe('Initial load empty state (404 / never connected)', () => {
    it('should show empty state with Connect button when getConnection 404s', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/pos/connection');
      expect(req.request.method).toBe('GET');
      req.flush(
        { message: 'No connection exists for this tenant' },
        { status: 404, statusText: 'Not Found' },
      );

      fixture.detectChanges();

      expect(component.isLoading()).toBeFalse();
      expect(component.connection()).toBeNull();
      expect(component.error()).toBeNull();

      const emptyCard = fixture.debugElement.query(By.css('[data-testid="empty-connection-card"]'));
      expect(emptyCard).not.toBeNull();

      const connectBtn = fixture.debugElement.query(By.css('[data-testid="connect-btn"]'));
      expect(connectBtn).not.toBeNull();

      const statusCard = fixture.debugElement.query(By.css('[data-testid="connection-status-card"]'));
      expect(statusCard).toBeNull();
    });
  });

  describe('Initial load connected state', () => {
    it('renders active state with account name, status, connected_at, and "Never synced yet" when last_synced_at is null', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/pos/connection');
      req.flush(mockActiveConnection);

      fixture.detectChanges();

      expect(component.isLoading()).toBeFalse();
      expect(component.connection()).toEqual(mockActiveConnection);

      const statusCard = fixture.debugElement.query(By.css('[data-testid="connection-status-card"]'));
      expect(statusCard).not.toBeNull();

      const displayNameEl = fixture.debugElement.query(By.css('[data-testid="connection-display-name"]'));
      expect(displayNameEl.nativeElement.textContent.trim()).toBe('Acme Square Store');

      const statusBadge = fixture.debugElement.query(By.css('[data-testid="connection-status-badge"]'));
      expect(statusBadge.nativeElement.textContent.trim()).toContain('Active');
      expect(statusBadge.nativeElement.classList).toContain('active');

      const connectedAtEl = fixture.debugElement.query(By.css('[data-testid="connection-connected-at"]'));
      expect(connectedAtEl).not.toBeNull();

      const lastSyncedEl = fixture.debugElement.query(By.css('[data-testid="connection-last-synced-at"]'));
      expect(lastSyncedEl.nativeElement.textContent.trim()).toBe('Never synced yet');

      const emptyCard = fixture.debugElement.query(By.css('[data-testid="empty-connection-card"]'));
      expect(emptyCard).toBeNull();
    });

    it('should display formatted last_synced_at when last_synced_at is not null', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/pos/connection');
      req.flush(mockNeedsReauthConnection);

      fixture.detectChanges();

      const lastSyncedEl = fixture.debugElement.query(By.css('[data-testid="connection-last-synced-at"]'));
      expect(lastSyncedEl.nativeElement.textContent.trim()).not.toBe('Never synced yet');
      expect(lastSyncedEl.nativeElement.textContent.trim().length).toBeGreaterThan(0);
    });

    it('renders disconnected state and disconnected_at when status is disconnected', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/pos/connection');
      req.flush(mockDisconnectedConnection);

      fixture.detectChanges();

      const statusBadge = fixture.debugElement.query(By.css('[data-testid="connection-status-badge"]'));
      expect(statusBadge.nativeElement.textContent.trim()).toContain('Disconnected');
      expect(statusBadge.nativeElement.classList).toContain('disconnected');

      const disconnectedAtEl = fixture.debugElement.query(By.css('[data-testid="connection-disconnected-at"]'));
      expect(disconnectedAtEl).not.toBeNull();
    });

    it('should handle generic load error (500) and allow retry', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/pos/connection');
      req.flush(
        { message: 'Database failure' },
        { status: 500, statusText: 'Internal Server Error' },
      );

      fixture.detectChanges();

      expect(component.isLoading()).toBeFalse();
      expect(component.connection()).toBeNull();
      expect(component.error()).toBe('pos.connection.loadError');

      const errorCard = fixture.debugElement.query(By.css('[data-testid="error-card"]'));
      expect(errorCard).not.toBeNull();

      // Retry
      const retryBtn = fixture.debugElement.query(By.css('[data-testid="retry-btn"]'));
      retryBtn.nativeElement.click();

      expect(component.isLoading()).toBeTrue();
      expect(component.error()).toBeNull();

      const retryReq = httpTestingController.expectOne('/api/v1/pos/connection');
      retryReq.flush(mockActiveConnection);

      fixture.detectChanges();

      expect(component.isLoading()).toBeFalse();
      expect(component.connection()).toEqual(mockActiveConnection);
      expect(fixture.debugElement.query(By.css('[data-testid="connection-status-card"]'))).not.toBeNull();
    });
  });

  describe('Connect flow and browser navigation', () => {
    it('connect button triggers navigation to the authorization URL', () => {
      spyOn(component, 'redirectToUrl');

      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/pos/connection').flush(
        { message: 'Not found' },
        { status: 404, statusText: 'Not Found' },
      );
      fixture.detectChanges();

      const connectBtn = fixture.debugElement.query(By.css('[data-testid="connect-btn"]'));
      connectBtn.nativeElement.click();

      expect(component.isMutating()).toBeTrue();

      const req = httpTestingController.expectOne('/api/v1/pos/connect');
      expect(req.request.method).toBe('POST');
      req.flush({ authorization_url: 'https://connect.squareup.com/oauth2/authorize?client_id=test' });

      expect(component.isMutating()).toBeFalse();
      expect(component.redirectToUrl).toHaveBeenCalledWith(
        'https://connect.squareup.com/oauth2/authorize?client_id=test',
      );
    });

    it('should show snackbar error when connect fails', () => {
      spyOn(component, 'redirectToUrl');

      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/pos/connection').flush(
        { message: 'Not found' },
        { status: 404, statusText: 'Not Found' },
      );
      fixture.detectChanges();

      const connectBtn = fixture.debugElement.query(By.css('[data-testid="connect-btn"]'));
      connectBtn.nativeElement.click();

      const req = httpTestingController.expectOne('/api/v1/pos/connect');
      req.flush(
        { message: 'Failed to mint authorization URL' },
        { status: 500, statusText: 'Internal Server Error' },
      );

      expect(component.isMutating()).toBeFalse();
      expect(component.redirectToUrl).not.toHaveBeenCalled();
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'pos.connection.startFailed',
        undefined,
        jasmine.objectContaining({ duration: 4000 }),
      );
    });
  });

  describe('Disconnect flow (role-gated)', () => {
    it('disconnect button calls the disconnect API and updates status for owner', () => {
      mockRoleSignal.set('owner');
      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/pos/connection').flush(mockActiveConnection);
      fixture.detectChanges();

      const disconnectBtn = fixture.debugElement.query(By.css('[data-testid="disconnect-btn"]'));
      expect(disconnectBtn).not.toBeNull();

      disconnectBtn.nativeElement.click();
      expect(component.isMutating()).toBeTrue();

      const req = httpTestingController.expectOne('/api/v1/pos/disconnect');
      expect(req.request.method).toBe('POST');
      req.flush({
        ...mockActiveConnection,
        status: 'disconnected',
        disconnected_at: '2026-09-19T12:00:00Z',
      });

      fixture.detectChanges();

      expect(component.isMutating()).toBeFalse();
      expect(component.connection()?.status).toBe('disconnected');
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'pos.connection.disconnectSuccess',
        undefined,
        jasmine.objectContaining({ duration: 3000 }),
      );

      const statusBadge = fixture.debugElement.query(By.css('[data-testid="connection-status-badge"]'));
      expect(statusBadge.nativeElement.textContent.trim()).toContain('Disconnected');
    });

    it('disconnect button hidden for non-owner and shows owner notice', () => {
      mockRoleSignal.set('buyer');
      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/pos/connection').flush(mockActiveConnection);
      fixture.detectChanges();

      const disconnectBtn = fixture.debugElement.query(By.css('[data-testid="disconnect-btn"]'));
      expect(disconnectBtn).toBeNull();

      const ownerNotice = fixture.debugElement.query(By.css('[data-testid="owner-notice"]'));
      expect(ownerNotice).not.toBeNull();
    });

    it('should show snackbar error when disconnect fails', () => {
      mockRoleSignal.set('owner');
      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/pos/connection').flush(mockActiveConnection);
      fixture.detectChanges();

      const disconnectBtn = fixture.debugElement.query(By.css('[data-testid="disconnect-btn"]'));
      disconnectBtn.nativeElement.click();

      const req = httpTestingController.expectOne('/api/v1/pos/disconnect');
      req.flush(
        { message: 'Disconnect failed' },
        { status: 500, statusText: 'Internal Server Error' },
      );

      expect(component.isMutating()).toBeFalse();
      expect(component.connection()?.status).toBe('active');
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'pos.connection.disconnectFailed',
        undefined,
        jasmine.objectContaining({ duration: 4000 }),
      );
    });
  });

  describe('Needs re-authorization banner', () => {
    it('renders needs-reauth banner and Reconnect button when status is needs_reauth', () => {
      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/pos/connection').flush(mockNeedsReauthConnection);
      fixture.detectChanges();

      const banner = fixture.debugElement.query(By.css('[data-testid="needs-reauth-banner"]'));
      expect(banner).not.toBeNull();

      const reconnectBtn = fixture.debugElement.query(By.css('[data-testid="reconnect-btn"]'));
      expect(reconnectBtn).not.toBeNull();
    });

    it('should not show needs-reauth banner when status is active or disconnected', () => {
      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/pos/connection').flush(mockActiveConnection);
      fixture.detectChanges();

      const banner = fixture.debugElement.query(By.css('[data-testid="needs-reauth-banner"]'));
      expect(banner).toBeNull();
    });

    it('should trigger connect flow when Reconnect button is clicked in banner', () => {
      spyOn(component, 'redirectToUrl');

      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/pos/connection').flush(mockNeedsReauthConnection);
      fixture.detectChanges();

      const reconnectBtn = fixture.debugElement.query(By.css('[data-testid="reconnect-btn"]'));
      reconnectBtn.nativeElement.click();

      expect(component.isMutating()).toBeTrue();

      const req = httpTestingController.expectOne('/api/v1/pos/connect');
      req.flush({ authorization_url: 'https://connect.squareup.com/oauth2/authorize?reauth=1' });

      expect(component.redirectToUrl).toHaveBeenCalledWith(
        'https://connect.squareup.com/oauth2/authorize?reauth=1',
      );
    });
  });

  describe('OAuth callback query parameters', () => {
    it('should display success snackbar and clean query param when pos_connected=success is present', fakeAsync(() => {
      mockQueryParamMap.set('pos_connected', 'success');

      component.ngOnInit();
      tick();

      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'pos.connection.connectedSuccess',
        undefined,
        jasmine.objectContaining({ duration: 3000 }),
      );

      expect(router.navigate).toHaveBeenCalledWith([], {
        relativeTo: jasmine.any(Object),
        queryParams: { pos_connected: null },
        queryParamsHandling: 'merge',
        replaceUrl: true,
      });

      httpTestingController.expectOne('/api/v1/pos/connection').flush(mockActiveConnection);
    }));

    it('should display error snackbar and clean query param when pos_connected=failed is present', fakeAsync(() => {
      mockQueryParamMap.set('pos_connected', 'failed');

      component.ngOnInit();
      tick();

      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'pos.connection.connectFailed',
        undefined,
        jasmine.objectContaining({ duration: 4000 }),
      );

      expect(router.navigate).toHaveBeenCalledWith([], {
        relativeTo: jasmine.any(Object),
        queryParams: { pos_connected: null },
        queryParamsHandling: 'merge',
        replaceUrl: true,
      });

      httpTestingController.expectOne('/api/v1/pos/connection').flush(
        { message: 'Not found' },
        { status: 404, statusText: 'Not Found' },
      );
    }));
  });
});
