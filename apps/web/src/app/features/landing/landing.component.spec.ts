import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';

import { environment } from '../../../environments/environment';
import { LandingComponent, ScreenshotCard } from './landing.component';

describe('LandingComponent', () => {
  let component: LandingComponent;
  let fixture: ComponentFixture<LandingComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LandingComponent],
      providers: [provideRouter([]), provideTranslateService()],
    }).compileComponents();

    fixture = TestBed.createComponent(LandingComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('creates the component', () => {
    expect(component).toBeTruthy();
  });

  it('renders the hero section with headline and lede', () => {
    const headlineEl = fixture.debugElement.query(By.css('.hero-headline'));
    expect(headlineEl).toBeTruthy();
    expect(headlineEl.nativeElement.textContent.trim()).toBe('landing.hero.headline');

    const ledeEl = fixture.debugElement.query(By.css('.hero-lede'));
    expect(ledeEl).toBeTruthy();
    expect(ledeEl.nativeElement.textContent.trim()).toBe('landing.hero.lede');
  });

  it('points the sign-in links to /auth/sign-in', () => {
    const headerSignIn = fixture.debugElement.query(By.css('.header-signin-btn'));
    expect(headerSignIn).toBeTruthy();
    expect(headerSignIn.nativeElement.getAttribute('routerLink') ?? headerSignIn.nativeElement.getAttribute('href')).toMatch(/\/auth\/sign-in/);

    const heroSignIn = fixture.debugElement.query(By.css('.hero-primary-btn'));
    expect(heroSignIn).toBeTruthy();
    expect(heroSignIn.nativeElement.getAttribute('routerLink') ?? heroSignIn.nativeElement.getAttribute('href')).toMatch(/\/auth\/sign-in/);
  });

  it('points the request pilot access link to mailto:<supportEmail>', () => {
    const requestAccess = fixture.debugElement.query(By.css('.hero-secondary-btn'));
    expect(requestAccess).toBeTruthy();
    expect(requestAccess.nativeElement.getAttribute('href')).toBe(`mailto:${environment.supportEmail}`);
  });

  it('does not render the gallery section when screenshotCards array is empty', () => {
    expect(component.screenshotCards().length).toBe(0);
    const gallerySection = fixture.debugElement.query(By.css('.gallery-section'));
    expect(gallerySection).toBeNull();
  });

  it('renders the gallery section and cards when screenshotCards array is non-empty', () => {
    const mockCard: ScreenshotCard = {
      src: 'assets/screenshots/preview.png',
      alt: 'landing.gallery.title',
      captionKey: 'landing.gallery.title',
    };

    component.screenshotCards.set([mockCard]);
    fixture.detectChanges();

    const gallerySection = fixture.debugElement.query(By.css('.gallery-section'));
    expect(gallerySection).not.toBeNull();

    const cardElements = fixture.debugElement.queryAll(By.css('.gallery-card'));
    expect(cardElements.length).toBe(1);

    // Clicking card opens modal
    cardElements[0].triggerEventHandler('click', null);
    fixture.detectChanges();

    expect(component.activeScreenshot()).toBe(mockCard);
    const modalEl = fixture.debugElement.query(By.css('.modal-backdrop'));
    expect(modalEl).not.toBeNull();

    // Closing modal resets activeScreenshot
    component.closeModal();
    fixture.detectChanges();
    expect(component.activeScreenshot()).toBeNull();
  });

  it('renders the How It Works three-step section', () => {
    const stepCards = fixture.debugElement.queryAll(By.css('.step-card'));
    expect(stepCards.length).toBe(3);
  });

  it('renders the footer with support mailto and copyright line', () => {
    const supportLink = fixture.debugElement.query(By.css('.footer-support-link'));
    expect(supportLink).toBeTruthy();
    expect(supportLink.nativeElement.getAttribute('href')).toBe(`mailto:${environment.supportEmail}`);

    const copyright = fixture.debugElement.query(By.css('.footer-copyright'));
    expect(copyright).toBeTruthy();
    expect(copyright.nativeElement.textContent.trim()).toBe('landing.footer.copyright');
  });
});
