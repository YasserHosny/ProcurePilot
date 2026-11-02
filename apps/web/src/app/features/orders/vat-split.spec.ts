import { splitVatInclusiveLine } from './vat-split';

describe('splitVatInclusiveLine', () => {
  it('splits 13.80 × 100 at 0.15 → net 12, netTotal 1200, tax 180, lineTotal 1380', () => {
    const result = splitVatInclusiveLine('13.80', 100, '0.15');
    expect(result.netUnitPrice).toBe(12);
    expect(result.netTotal).toBe(1200);
    expect(result.tax).toBe(180);
    expect(result.lineTotal).toBe(1380);
  });

  it('splits 10.00 × 3 at 0.15 → net 8.6957, netTotal 26.0871, tax 3.9129, lineTotal 30', () => {
    const result = splitVatInclusiveLine('10.00', 3, '0.15');
    expect(result.netUnitPrice).toBe(8.6957);
    expect(result.netTotal).toBe(26.0871);
    expect(result.tax).toBe(3.9129);
    expect(result.lineTotal).toBe(30);
  });

  it('splits lines 82×15, 150×10, 38×10, 86×20 at 0.15 → Σ lineTotal = 4830 exactly and Σ netTotal + Σ tax = 4830', () => {
    const l1 = splitVatInclusiveLine('82', 15, '0.15');
    const l2 = splitVatInclusiveLine('150', 10, '0.15');
    const l3 = splitVatInclusiveLine('38', 10, '0.15');
    const l4 = splitVatInclusiveLine('86', 20, '0.15');

    expect(l1.netUnitPrice).toBe(71.3043);
    expect(l1.netTotal).toBe(1069.5645);
    expect(l1.tax).toBe(160.4355);
    expect(l1.lineTotal).toBe(1230);

    expect(l2.netUnitPrice).toBe(130.4348);
    expect(l2.netTotal).toBe(1304.348);
    expect(l2.tax).toBe(195.652);
    expect(l2.lineTotal).toBe(1500);

    expect(l3.netUnitPrice).toBe(33.0435);
    expect(l3.netTotal).toBe(330.435);
    expect(l3.tax).toBe(49.565);
    expect(l3.lineTotal).toBe(380);

    expect(l4.netUnitPrice).toBe(74.7826);
    expect(l4.netTotal).toBe(1495.652);
    expect(l4.tax).toBe(224.348);
    expect(l4.lineTotal).toBe(1720);

    const sumLineTotal = l1.lineTotal + l2.lineTotal + l3.lineTotal + l4.lineTotal;
    const sumNetTotal = l1.netTotal + l2.netTotal + l3.netTotal + l4.netTotal;
    const sumTax = l1.tax + l2.tax + l3.tax + l4.tax;

    expect(sumLineTotal).toBe(4830);
    expect(Math.round((sumNetTotal + sumTax) * 10000) / 10000).toBe(4830);
  });
});
