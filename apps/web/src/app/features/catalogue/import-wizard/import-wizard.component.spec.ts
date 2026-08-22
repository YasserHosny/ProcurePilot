import { ComponentFixture, TestBed } from "@angular/core/testing";
import { signal } from "@angular/core";
import { ActivatedRoute, provideRouter } from "@angular/router";
import { TranslateModule, TranslateService } from "@ngx-translate/core";
import { of } from "rxjs";

import enCatalog from "../../../../../../../packages/i18n/en.json";
import { ApiService } from "../../../core/api/api.service";
import type { ImportPreview, ImportResult, Role } from "../../../core/api/models";
import { SessionService } from "../../../core/auth/session.service";
import { ImportWizardComponent } from "./import-wizard.component";

describe("ImportWizardComponent (T033)", () => {
  let component: ImportWizardComponent;
  let fixture: ComponentFixture<ImportWizardComponent>;
  let apiService: jasmine.SpyObj<ApiService>;

  beforeEach(async () => {
    apiService = jasmine.createSpyObj("ApiService", ["uploadImport", "commitImport"]);

    const mockSession = {
      hasRole: jasmine.createSpy("hasRole").and.returnValue(true),
      role: signal<Role | null>("buyer"),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal("en"),
    };

    await TestBed.configureTestingModule({
      imports: [ImportWizardComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: mockSession },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              queryParamMap: {
                get: (key: string) => (key === "kind" ? "products" : null),
              },
            },
          },
        },
      ],
    }).compileComponents();

    const translate = TestBed.inject(TranslateService);
    translate.setTranslation("en", enCatalog);
    translate.use("en");

    fixture = TestBed.createComponent(ImportWizardComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it("should show error report with line numbers when file has validation errors (nothing saved)", () => {
    const mockInvalidPreview: ImportPreview = {
      import_id: "imp-1",
      kind: "products",
      row_count: 5,
      valid: false,
      errors: [
        { line: 3, column: "pack_count", reason: "Pack count must be positive integer" },
      ],
      missing_columns: [],
      unrecognised_columns: [],
    };
    apiService.uploadImport.and.returnValue(of(mockInvalidPreview));

    const testFile = new File(["dummy,content"], "products.csv", { type: "text/csv" });
    component.selectedFile.set(testFile);
    component.uploadAndValidate();

    expect(component.currentStep()).toBe("preview");
    expect(component.previewData()?.valid).toBeFalse();
    expect(component.previewData()?.errors[0].line).toBe(3);
  });

  it("should commit import and advance to result when confirmed for valid preview", () => {
    const mockValidPreview: ImportPreview = {
      import_id: "imp-valid",
      kind: "products",
      row_count: 2,
      valid: true,
      errors: [],
      preview: [{ tenant_name: "Milk", base_unit: "litre" }],
    };
    const mockResult: ImportResult = {
      import_id: "imp-valid",
      created: 2,
      skipped: 0,
      updated: 0,
    };
    apiService.uploadImport.and.returnValue(of(mockValidPreview));
    apiService.commitImport.and.returnValue(of(mockResult));

    const testFile = new File(["name,unit"], "valid.csv", { type: "text/csv" });
    component.selectedFile.set(testFile);
    component.uploadAndValidate();

    expect(component.previewData()?.valid).toBeTrue();

    component.confirmImport();

    expect(apiService.commitImport).toHaveBeenCalledWith("imp-valid", "skip");
    expect(component.currentStep()).toBe("result");
    expect(component.importResult()?.created).toBe(2);
  });
});
