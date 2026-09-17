import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { type WritableSignal, signal } from '@angular/core';
import { ComponentFixture, TestBed, fakeAsync, tick } from '@angular/core/testing';
import { MatSnackBar } from '@angular/material/snack-bar';
import { By } from '@angular/platform-browser';
import { provideNoopAnimations } from '@angular/platform-browser/animations';
import { provideRouter } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';

import type { Role } from '../../../core/api/models';
import { SessionService } from '../../../core/auth/session.service';
import type { TenantEmailConfig } from '../ingestion-api';
import { EmailConfigComponent } from './email-config.component';

describe('EmailConfigComponent (T022)', () => {
  let component: EmailConfigComponent;
  let fixture: ComponentFixture<EmailConfigComponent>;
  let httpTestingController: HttpTestingController;
  let mockRoleSignal: WritableSignal<Role | null>;
  let snackBarSpy: jasmine.SpyObj<MatSnackBar>;
  let writeTextSpy: jasmine.Spy;

  const mockConfig: TenantEmailConfig = {
    id: 'cfg-001',
    forwarding_address: 'inbound-test@procurepilot.com',
    enabled: true,
    domain_allowlist: ['supplier.com', 'vendor.org'],
    daily_limit: 500,
    daily_count: 24,
    daily_count_date: '2026-09-17',
    spf_dkim_required: true,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-17T08:00:00Z',
  };

  beforeEach(async () => {
    mockRoleSignal = signal<Role | null>('owner');
    snackBarSpy = jasmine.createSpyObj('MatSnackBar', ['open']);
    writeTextSpy = jasmine.createSpy('writeText').and.returnValue(Promise.resolve());

    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: writeTextSpy },
      configurable: true,
      writable: true,
    });

    const mockSessionService = {
      role: mockRoleSignal,
      hasRole: (...roles: readonly Role[]) => {
        const current = mockRoleSignal();
        return current !== null && roles.includes(current);
      },
    };

    await TestBed.configureTestingModule({
      imports: [EmailConfigComponent, TranslateModule.forRoot()],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideNoopAnimations(),
        provideRouter([]),
        { provide: SessionService, useValue: mockSessionService },
      ],
    })
      .overrideComponent(EmailConfigComponent, {
        set: {
          providers: [{ provide: MatSnackBar, useValue: snackBarSpy }],
        },
      })
      .compileComponents();

    httpTestingController = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(EmailConfigComponent);
    component = fixture.componentInstance;
  });

  afterEach(() => {
    httpTestingController.verify();
  });

  it('should create the component', () => {
    expect(component).toBeTruthy();
  });

  describe('Initial load', () => {
    it('should fetch TenantEmailConfig on init and render values', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/tenants/email-config');
      expect(req.request.method).toBe('GET');
      req.flush(mockConfig);

      fixture.detectChanges();

      expect(component.isLoading()).toBeFalse();
      expect(component.error()).toBeNull();
      expect(component.config()).toEqual(mockConfig);

      const addressEl = fixture.debugElement.query(By.css('[data-testid="forwarding-address"]'));
      expect(addressEl).not.toBeNull();
      expect(addressEl.nativeElement.textContent.trim()).toBe('inbound-test@procurepilot.com');

      const countEl = fixture.debugElement.query(By.css('[data-testid="daily-count"]'));
      expect(countEl.nativeElement.textContent.trim()).toBe('24');

      const limitEl = fixture.debugElement.query(By.css('[data-testid="daily-limit"]'));
      expect(limitEl.nativeElement.textContent.trim()).toBe('500');
    });

    it('should handle load error and allow retry', () => {
      fixture.detectChanges();

      const req = httpTestingController.expectOne('/api/v1/tenants/email-config');
      req.flush(
        { message: 'Service unavailable' },
        { status: 503, statusText: 'Service Unavailable' }
      );

      fixture.detectChanges();

      expect(component.isLoading()).toBeFalse();
      expect(component.config()).toBeNull();
      expect(component.error()).toBe('ingestion.emailConfig.loadError');

      const errorCard = fixture.debugElement.query(By.css('.error-card'));
      expect(errorCard).not.toBeNull();

      // Retry
      component.loadConfig();
      expect(component.isLoading()).toBeTrue();
      expect(component.error()).toBeNull();

      const retryReq = httpTestingController.expectOne('/api/v1/tenants/email-config');
      retryReq.flush(mockConfig);

      fixture.detectChanges();

      expect(component.isLoading()).toBeFalse();
      expect(component.config()).toEqual(mockConfig);
    });
  });

  describe('Enable/disable toggle', () => {
    it('should disable email ingestion when toggle is turned off by owner', () => {
      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/tenants/email-config').flush(mockConfig);
      fixture.detectChanges();

      expect(component.config()?.enabled).toBeTrue();

      component.toggleEnabled();
      expect(component.isMutating()).toBeTrue();

      const req = httpTestingController.expectOne('/api/v1/tenants/email-config/disable');
      expect(req.request.method).toBe('POST');
      req.flush({ ...mockConfig, enabled: false });

      expect(component.isMutating()).toBeFalse();
      expect(component.config()?.enabled).toBeFalse();
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'ingestion.emailConfig.disabledSuccess',
        undefined,
        jasmine.objectContaining({ duration: 3000 })
      );
    });

    it('should enable email ingestion when toggle is turned on by owner', () => {
      const disabledConfig = { ...mockConfig, enabled: false };
      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/tenants/email-config').flush(disabledConfig);
      fixture.detectChanges();

      expect(component.config()?.enabled).toBeFalse();

      component.toggleEnabled();
      expect(component.isMutating()).toBeTrue();

      const req = httpTestingController.expectOne('/api/v1/tenants/email-config/enable');
      expect(req.request.method).toBe('POST');
      req.flush({ ...disabledConfig, enabled: true });

      expect(component.isMutating()).toBeFalse();
      expect(component.config()?.enabled).toBeTrue();
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'ingestion.emailConfig.enabledSuccess',
        undefined,
        jasmine.objectContaining({ duration: 3000 })
      );
    });

    it('should handle toggle mutation error gracefully', () => {
      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/tenants/email-config').flush(mockConfig);
      fixture.detectChanges();

      component.toggleEnabled();

      const req = httpTestingController.expectOne('/api/v1/tenants/email-config/disable');
      req.flush(
        { message: 'Permission denied' },
        { status: 403, statusText: 'Forbidden' }
      );

      expect(component.isMutating()).toBeFalse();
      expect(component.config()?.enabled).toBeTrue();
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'ingestion.emailConfig.updateFailed',
        undefined,
        jasmine.objectContaining({ duration: 4000 })
      );
    });

    it('should display toggle when user is owner', () => {
      mockRoleSignal.set('owner');
      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/tenants/email-config').flush(mockConfig);
      fixture.detectChanges();

      const toggle = fixture.debugElement.query(By.css('[data-testid="toggle-enabled"]'));
      expect(toggle).not.toBeNull();

      const notice = fixture.debugElement.query(By.css('.owner-notice'));
      expect(notice).toBeNull();
    });

    it('should hide toggle and show owner notice when user is not owner', () => {
      mockRoleSignal.set('buyer');
      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/tenants/email-config').flush(mockConfig);
      fixture.detectChanges();

      const toggle = fixture.debugElement.query(By.css('[data-testid="toggle-enabled"]'));
      expect(toggle).toBeNull();

      const notice = fixture.debugElement.query(By.css('.owner-notice'));
      expect(notice).not.toBeNull();
    });
  });

  describe('Domain allowlist editor', () => {
    beforeEach(() => {
      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/tenants/email-config').flush(mockConfig);
      fixture.detectChanges();
    });

    it('should add a new domain and PUT full allowlist array', () => {
      component.newDomain.set('acme-parts.com');
      component.addDomain();

      expect(component.isMutating()).toBeTrue();

      const req = httpTestingController.expectOne('/api/v1/tenants/email-config');
      expect(req.request.method).toBe('PUT');
      expect(req.request.body).toEqual({
        domain_allowlist: ['supplier.com', 'vendor.org', 'acme-parts.com'],
      });

      const updated = {
        ...mockConfig,
        domain_allowlist: ['supplier.com', 'vendor.org', 'acme-parts.com'],
      };
      req.flush(updated);

      expect(component.isMutating()).toBeFalse();
      expect(component.newDomain()).toBe('');
      expect(component.config()?.domain_allowlist).toEqual([
        'supplier.com',
        'vendor.org',
        'acme-parts.com',
      ]);
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'ingestion.emailConfig.updateSuccess',
        undefined,
        jasmine.objectContaining({ duration: 3000 })
      );
    });

    it('should reject duplicate domain without HTTP call', () => {
      component.newDomain.set('supplier.com');
      component.addDomain();

      httpTestingController.expectNone('/api/v1/tenants/email-config');
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'ingestion.emailConfig.duplicateDomain',
        undefined,
        jasmine.objectContaining({ duration: 3000 })
      );
    });

    it('should reject invalid domain without HTTP call', () => {
      component.newDomain.set('invalid domain');
      component.addDomain();

      httpTestingController.expectNone('/api/v1/tenants/email-config');
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'ingestion.emailConfig.invalidDomain',
        undefined,
        jasmine.objectContaining({ duration: 3000 })
      );
    });

    it('should ignore empty or whitespace domain input', () => {
      component.newDomain.set('   ');
      component.addDomain();

      httpTestingController.expectNone('/api/v1/tenants/email-config');
      expect(snackBarSpy.open).not.toHaveBeenCalled();
    });

    it('should remove domain and PUT updated allowlist array', () => {
      component.removeDomain('supplier.com');

      expect(component.isMutating()).toBeTrue();

      const req = httpTestingController.expectOne('/api/v1/tenants/email-config');
      expect(req.request.method).toBe('PUT');
      expect(req.request.body).toEqual({
        domain_allowlist: ['vendor.org'],
      });

      const updated = {
        ...mockConfig,
        domain_allowlist: ['vendor.org'],
      };
      req.flush(updated);

      expect(component.isMutating()).toBeFalse();
      expect(component.config()?.domain_allowlist).toEqual(['vendor.org']);
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'ingestion.emailConfig.updateSuccess',
        undefined,
        jasmine.objectContaining({ duration: 3000 })
      );
    });

    it('should show empty allowlist notice when list is empty', () => {
      component.removeDomain('supplier.com');
      httpTestingController
        .expectOne('/api/v1/tenants/email-config')
        .flush({ ...mockConfig, domain_allowlist: ['vendor.org'] });

      component.removeDomain('vendor.org');
      httpTestingController
        .expectOne('/api/v1/tenants/email-config')
        .flush({ ...mockConfig, domain_allowlist: [] });

      fixture.detectChanges();

      const emptyNotice = fixture.debugElement.query(By.css('.empty-allowlist-notice'));
      expect(emptyNotice).not.toBeNull();
    });
  });

  describe('Copy to clipboard', () => {
    it('should copy forwarding address and show confirmation snackbar', fakeAsync(() => {
      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/tenants/email-config').flush(mockConfig);
      fixture.detectChanges();

      component.copyAddress();
      tick();

      expect(writeTextSpy).toHaveBeenCalledWith('inbound-test@procurepilot.com');
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'ingestion.emailConfig.copySuccess',
        undefined,
        jasmine.objectContaining({ duration: 3000 })
      );
    }));

    it('should show error snackbar when clipboard writeText fails', fakeAsync(() => {
      writeTextSpy.and.returnValue(Promise.reject(new Error('Clipboard blocked')));

      fixture.detectChanges();
      httpTestingController.expectOne('/api/v1/tenants/email-config').flush(mockConfig);
      fixture.detectChanges();

      component.copyAddress();
      tick();

      expect(writeTextSpy).toHaveBeenCalledWith('inbound-test@procurepilot.com');
      expect(snackBarSpy.open).toHaveBeenCalledWith(
        'ingestion.emailConfig.copyError',
        undefined,
        jasmine.objectContaining({ duration: 4000 })
      );
    }));

    it('should do nothing when forwarding address is not available', fakeAsync(() => {
      component.config.set(null);
      component.copyAddress();
      tick();

      expect(writeTextSpy).not.toHaveBeenCalled();
      expect(snackBarSpy.open).not.toHaveBeenCalled();
    }));
  });
});
