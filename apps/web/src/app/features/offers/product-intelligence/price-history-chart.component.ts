import { Component, Input, OnChanges, SimpleChanges, signal } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslatePipe } from '@ngx-translate/core';

import { FormatDatePipe } from '../../../core/format/date.pipe';
import { FormatMoneyPipe } from '../../../core/format/money.pipe';
import type { PriceHistoryPoint } from '../offers-api';

export interface ChartPoint {
  readonly x: number;
  readonly y: number;
  readonly raw: PriceHistoryPoint;
  readonly color: string;
}

export interface SupplierSeries {
  readonly supplierId: string;
  readonly supplierName: string;
  readonly color: string;
  readonly points: readonly ChartPoint[];
  readonly pathD: string;
}

const PALETTE = [
  '#2563eb', // blue
  '#059669', // emerald
  '#d97706', // amber
  '#7c3aed', // violet
  '#dc2626', // red
  '#0891b2', // cyan
  '#db2777', // pink
];

@Component({
  selector: 'app-price-history-chart',
  standalone: true,
  imports: [
    MatCardModule,
    MatIconModule,
    MatTooltipModule,
    TranslatePipe,
    FormatDatePipe,
    FormatMoneyPipe,
  ],
  templateUrl: './price-history-chart.component.html',
  styleUrl: './price-history-chart.component.scss',
})
export class PriceHistoryChartComponent implements OnChanges {
  @Input() points: readonly PriceHistoryPoint[] = [];
  @Input() currency = 'GBP';

  readonly hoveredPoint = signal<ChartPoint | null>(null);

  readonly width = 800;
  readonly height = 320;
  readonly padding = { top: 30, right: 40, bottom: 45, left: 70 };

  readonly seriesList = signal<SupplierSeries[]>([]);
  readonly yTicks = signal<{ y: number; label: string }[]>([]);
  readonly xTicks = signal<{ x: number; label: string }[]>([]);

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['points']) {
      this.computeChart();
    }
  }

  private computeChart(): void {
    if (!this.points || this.points.length === 0) {
      this.seriesList.set([]);
      this.yTicks.set([]);
      this.xTicks.set([]);
      return;
    }

    const plotWidth = this.width - this.padding.left - this.padding.right;
    const plotHeight = this.height - this.padding.top - this.padding.bottom;

    // Determine min/max timestamps and prices
    const timestamps = this.points.map((p) => new Date(p.recorded_at).getTime());
    const prices = this.points.map((p) => parseFloat(p.normalised_unit_price.amount) || 0);

    let minTime = Math.min(...timestamps);
    let maxTime = Math.max(...timestamps);
    if (minTime === maxTime) {
      minTime -= 7 * 24 * 3600 * 1000;
      maxTime += 7 * 24 * 3600 * 1000;
    }

    let minPrice = Math.min(...prices);
    let maxPrice = Math.max(...prices);
    if (minPrice === maxPrice) {
      minPrice = Math.max(0, minPrice * 0.8);
      maxPrice = maxPrice * 1.2 || 10;
    } else {
      const pricePadding = (maxPrice - minPrice) * 0.15;
      minPrice = Math.max(0, minPrice - pricePadding);
      maxPrice = maxPrice + pricePadding;
    }

    // Group by supplier
    const supplierMap = new Map<string, { name: string; points: PriceHistoryPoint[] }>();
    for (const pt of this.points) {
      const existing = supplierMap.get(pt.supplier_id);
      if (existing) {
        existing.points.push(pt);
      } else {
        supplierMap.set(pt.supplier_id, { name: pt.supplier_name, points: [pt] });
      }
    }

    let colorIdx = 0;
    const resultSeries: SupplierSeries[] = [];

    supplierMap.forEach((val, suppId) => {
      const color = PALETTE[colorIdx % PALETTE.length];
      colorIdx++;

      // Sort chronologically
      const sorted = [...val.points].sort(
        (a, b) => new Date(a.recorded_at).getTime() - new Date(b.recorded_at).getTime(),
      );

      const chartPoints: ChartPoint[] = sorted.map((pt) => {
        const t = new Date(pt.recorded_at).getTime();
        const p = parseFloat(pt.normalised_unit_price.amount) || 0;

        const x = this.padding.left + ((t - minTime) / (maxTime - minTime)) * plotWidth;
        const y = this.padding.top + plotHeight - ((p - minPrice) / (maxPrice - minPrice)) * plotHeight;

        return { x, y, raw: pt, color };
      });

      // Generate SVG path if multiple points
      let pathD = '';
      if (chartPoints.length > 1) {
        pathD = `M ${chartPoints[0].x} ${chartPoints[0].y}`;
        for (let i = 1; i < chartPoints.length; i++) {
          pathD += ` L ${chartPoints[i].x} ${chartPoints[i].y}`;
        }
      }

      resultSeries.push({
        supplierId: suppId,
        supplierName: val.name,
        color,
        points: chartPoints,
        pathD,
      });
    });

    this.seriesList.set(resultSeries);

    // Compute Y-axis ticks (4 intervals)
    const yTickCount = 4;
    const ticksY: { y: number; label: string }[] = [];
    for (let i = 0; i <= yTickCount; i++) {
      const val = minPrice + ((maxPrice - minPrice) * i) / yTickCount;
      const y = this.padding.top + plotHeight - (i / yTickCount) * plotHeight;
      ticksY.push({ y, label: val.toFixed(2) });
    }
    this.yTicks.set(ticksY);

    // Compute X-axis ticks (3 intervals)
    const xTickCount = 3;
    const ticksX: { x: number; label: string }[] = [];
    for (let i = 0; i <= xTickCount; i++) {
      const t = minTime + ((maxTime - minTime) * i) / xTickCount;
      const x = this.padding.left + (i / xTickCount) * plotWidth;
      const d = new Date(t);
      const label = `${d.getDate()}/${d.getMonth() + 1}/${d.getFullYear().toString().slice(-2)}`;
      ticksX.push({ x, label });
    }
    this.xTicks.set(ticksX);
  }

  onPointHover(pt: ChartPoint | null): void {
    this.hoveredPoint.set(pt);
  }
}
