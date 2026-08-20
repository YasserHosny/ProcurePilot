import { Component, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';

import type { Role } from '../api/models';
import { RoleDirective } from './role.directive';
import { SessionService } from './session.service';

@Component({
  standalone: true,
  imports: [RoleDirective],
  template: `
    <div id="owner-only" *appRole="'owner'">Owner Content</div>
    <div id="multi-role" *appRole="['owner', 'buyer']">Multi Role Content</div>
    <div id="viewer-only" *appRole="'viewer'">Viewer Content</div>
  `,
})
class TestHostComponent {}

describe('RoleDirective (T060)', () => {
  let fixture: ComponentFixture<TestHostComponent>;
  let mockRoleSignal: ReturnType<typeof signal<Role | null>>;

  beforeEach(async () => {
    mockRoleSignal = signal<Role | null>('owner');

    const mockSessionService = {
      role: mockRoleSignal,
      hasRole: (...roles: readonly Role[]) => {
        const current = mockRoleSignal();
        return current !== null && roles.includes(current);
      },
    };

    await TestBed.configureTestingModule({
      imports: [TestHostComponent],
      providers: [{ provide: SessionService, useValue: mockSessionService }],
    }).compileComponents();

    fixture = TestBed.createComponent(TestHostComponent);
    fixture.detectChanges();
  });

  it('should render elements when the active role matches', () => {
    const ownerEl = fixture.debugElement.query(By.css('#owner-only'));
    const multiEl = fixture.debugElement.query(By.css('#multi-role'));
    const viewerEl = fixture.debugElement.query(By.css('#viewer-only'));

    expect(ownerEl).not.toBeNull();
    expect(multiEl).not.toBeNull();
    expect(viewerEl).toBeNull();
  });

  it('should update DOM dynamically when user role changes', () => {
    mockRoleSignal.set('buyer');
    fixture.detectChanges();

    const ownerEl = fixture.debugElement.query(By.css('#owner-only'));
    const multiEl = fixture.debugElement.query(By.css('#multi-role'));
    const viewerEl = fixture.debugElement.query(By.css('#viewer-only'));

    expect(ownerEl).toBeNull();
    expect(multiEl).not.toBeNull();
    expect(viewerEl).toBeNull();
  });

  it('should hide all role-restricted elements when role is null', () => {
    mockRoleSignal.set(null);
    fixture.detectChanges();

    const ownerEl = fixture.debugElement.query(By.css('#owner-only'));
    const multiEl = fixture.debugElement.query(By.css('#multi-role'));
    const viewerEl = fixture.debugElement.query(By.css('#viewer-only'));

    expect(ownerEl).toBeNull();
    expect(multiEl).toBeNull();
    expect(viewerEl).toBeNull();
  });
});
