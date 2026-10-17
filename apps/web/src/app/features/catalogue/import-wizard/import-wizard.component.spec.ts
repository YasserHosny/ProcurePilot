import { ComponentFixture, TestBed } from "@angular/core/testing";
import { signal } from "@angular/core";
import { ActivatedRoute, provideRouter } from "@angular/router";
import { TranslateModule, TranslateService } from "@ngx-translate/core";
import { of, throwError } from "rxjs";

import arCatalog from "../../../../../../../packages/i18n/ar.json";
import enCatalog from "../../../../../../../packages/i18n/en.json";
import { ApiService } from "../../../core/api/api.service";
import type { BaseUnit, ImportPreview, ImportResult, Locale, Role } from "../../../core/api/models";
import { SessionService } from "../../../core/auth/session.service";
import { I18nService } from "../../../core/i18n";
import { ImportWizardComponent } from "./import-wizard.component";
import { ImportWizardPreviewComponent } from "./import-wizard-preview.component";

describe("ImportWizardComponent (T033)", () => {
  let component: ImportWizardComponent;
  let fixture: ComponentFixture<ImportWizardComponent>;
  let apiService: jasmine.SpyObj<ApiService>;
  let localeSignal: ReturnType<typeof signal<Locale>>;

  const mockBaseUnits: BaseUnit[] = [
    { code: "kg", dimension: "mass", label_en: "kg", label_ar: "كجم" },
    { code: "litre", dimension: "volume", label_en: "L", label_ar: "لتر" },
  ];

  beforeEach(async () => {
    apiService = jasmine.createSpyObj("ApiService", [
      "uploadImport",
      "commitImport",
      "baseUnits",
    ]);
    apiService.baseUnits.and.returnValue(of({ items: mockBaseUnits }));

    localeSignal = signal<Locale>("en");

    const mockSession = {
      hasRole: jasmine.createSpy("hasRole").and.returnValue(true),
      role: signal<Role | null>("buyer"),
      currentMember: signal(null),
      isAuthenticated: signal(true),
      tenant: signal(null),
      activeLocale: signal("en"),
    };

    const mockI18n = {
      currentLocale: localeSignal,
    };

    await TestBed.configureTestingModule({
      imports: [ImportWizardComponent, ImportWizardPreviewComponent, TranslateModule.forRoot()],
      providers: [
        provideRouter([]),
        { provide: ApiService, useValue: apiService },
        { provide: SessionService, useValue: mockSession },
        { provide: I18nService, useValue: mockI18n },
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
    translate.setTranslation("ar", arCatalog);
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

  describe("ImportWizardPreviewComponent", () => {
    it("formats pack cell with localized unit label, strips trailing decimal zeros, and translates column headers", () => {
      const previewFixture = TestBed.createComponent(ImportWizardPreviewComponent);
      const previewComp = previewFixture.componentInstance;
      previewComp.preview = {
        import_id: "imp-pack",
        kind: "products",
        row_count: 2,
        valid: true,
        errors: [],
        preview: [
          {
            line: 2,
            tenant_name: "Flour",
            base_unit: "kg",
            pack: { pack_count: 1, unit_size: "25.000" },
            unknown_col: "val",
          },
          {
            line: 3,
            tenant_name: "Sugar",
            base_unit: "custom_unit",
            pack: { pack_count: 2, unit_size: "10" },
            unknown_col: "val2",
          },
        ],
      };
      previewComp.isWriter = true;
      previewComp.isCommitting = false;
      previewFixture.detectChanges();

      const el = previewFixture.nativeElement as HTMLElement;
      const headers = Array.from(el.querySelectorAll(".simple-preview-table thead th")).map((th) =>
        th.textContent?.trim(),
      );
      expect(headers).toEqual(["Row", "Product Name", "Base Unit", "Pack", "unknown_col"]);

      const rows = el.querySelectorAll(".simple-preview-table tbody tr");
      const firstRowCells = Array.from(rows[0].querySelectorAll("td")).map((td) =>
        td.textContent?.trim(),
      );
      const secondRowCells = Array.from(rows[1].querySelectorAll("td")).map((td) =>
        td.textContent?.trim(),
      );

      expect(firstRowCells[3]).toBe("1 × 25 kg");
      // Fallback to raw code when unit is not in baseUnits
      expect(secondRowCells[3]).toBe("2 × 10 custom_unit");

      // Switch to Arabic
      const translate = TestBed.inject(TranslateService);
      translate.use("ar");
      localeSignal.set("ar");
      previewFixture.detectChanges();

      const arHeaders = Array.from(el.querySelectorAll(".simple-preview-table thead th")).map(
        (th) => th.textContent?.trim(),
      );
      expect(arHeaders).toEqual(["الصف", "اسم المنتج", "وحدة القياس", "العبوة", "unknown_col"]);

      const arFirstRowCells = Array.from(
        el.querySelectorAll(".simple-preview-table tbody tr")[0].querySelectorAll("td"),
      ).map((td) => td.textContent?.trim());
      expect(arFirstRowCells[3]).toBe("1 × 25 كجم");
    });

    it("falls back to raw base_unit code when baseUnits API fails", () => {
      apiService.baseUnits.and.returnValue(throwError(() => new Error("Network error")));

      const previewFixture = TestBed.createComponent(ImportWizardPreviewComponent);
      const previewComp = previewFixture.componentInstance;
      previewComp.preview = {
        import_id: "imp-fallback",
        kind: "products",
        row_count: 1,
        valid: true,
        errors: [],
        preview: [
          {
            tenant_name: "Oil",
            base_unit: "litre",
            pack: { pack_count: 4, unit_size: "2.500" },
          },
        ],
      };
      previewComp.isWriter = true;
      previewComp.isCommitting = false;
      previewFixture.detectChanges();

      const row = previewFixture.nativeElement.querySelector(
        ".simple-preview-table tbody tr",
      ) as HTMLElement;
      const cells = Array.from(row.querySelectorAll("td")).map((td) => td.textContent?.trim());
      expect(cells[2]).toBe("4 × 2.5 litre");
    });
  });
});
