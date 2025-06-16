import { Component, OnInit, AfterViewInit, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatOptionModule } from '@angular/material/core';
import { MatTableModule, MatTableDataSource } from '@angular/material/table';
import { MatPaginatorModule, MatPaginator } from '@angular/material/paginator';
import { MatSortModule, MatSort } from '@angular/material/sort';
import { HttpClient } from '@angular/common/http';
import Chart from 'chart.js/auto';
import annotationPlugin, { BoxAnnotationOptions } from 'chartjs-plugin-annotation';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';

Chart.register(annotationPlugin);

interface ForecastData {
  date: string;
  forecastedDemand: string;
  remainingStockLevel: string;
  openingStockLevel: string;
  stockout: boolean;
}

@Component({
  selector: 'app-prediction',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatOptionModule,
    MatTableModule,
    MatPaginatorModule,
    MatSortModule,
    MatProgressSpinnerModule
  ],
  templateUrl: './prediction.component.html',
  styleUrls: ['./prediction.component.css']
})
export class PredictionComponent implements OnInit, AfterViewInit {
  productIds: string[] = [];
  selectedProductId: string = 'P00003';
  startDate: string = '2024-04-22';
  endDate: string = '2024-04-29';
  stockoutDates: string[] = [];
  isLoading: boolean = false;

  plotUrl: SafeResourceUrl | string = '';
  hasChartData: boolean = false;

  displayedColumns: string[] = [
    'openingStockLevel',
    'remainingStockLevel',
    'forecastedDemand',
    'stockout',
    'date'
  ];

  dataSource = new MatTableDataSource<ForecastData>([]);

  @ViewChild('forecastChart') forecastChart!: ElementRef<HTMLCanvasElement>;
  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;
  chart: Chart | undefined;

  // Hardcoded API base URL
  private apiBaseUrl: string = 'http://20.174.3.84:8000/';

  constructor(private http: HttpClient, private sanitizer: DomSanitizer) {}

  ngOnInit() {
    this.http.get<string[]>(`${this.apiBaseUrl}/products`).subscribe({
      next: (data) => {
        console.log('Product IDs:', data);
        this.productIds = data;
        if (!this.productIds.includes(this.selectedProductId) && this.productIds.length > 0) {
          this.selectedProductId = this.productIds[0];
        }
      },
      error: (error) => {
        console.error('Error fetching product IDs:', error);
        let errorMessage = 'Failed to fetch product IDs. Please try again later.';
        if (error.status === 0) {
          errorMessage += ` (Possible CORS or network issue. Check if the API server is running at ${this.apiBaseUrl}.)`;
        } else if (error.status) {
          errorMessage += ` (HTTP ${error.status}: ${error.statusText})`;
        }
        alert(errorMessage);
      }
    });
  }

  ngAfterViewInit() {
    console.log('ngAfterViewInit - Canvas available:', !!this.forecastChart);
    this.dataSource.paginator = this.paginator;
    this.dataSource.sort = this.sort;
  }

  onSubmit() {
    if (!this.selectedProductId || !this.startDate || !this.endDate) {
      alert('Please fill in all fields');
      return;
    }

    this.isLoading = true;
    this.stockoutDates = [];
    this.dataSource.data = [];
    this.plotUrl = '';
    this.hasChartData = false;

    if (this.chart) {
      this.chart.destroy();
      this.chart = undefined;
    }

    const request = {
      product_id: this.selectedProductId,
      start_date: this.startDate,
      end_date: this.endDate
    };

    this.http.post<any>(`${this.apiBaseUrl}/predict`, request).subscribe({
      next: (response) => {
        console.log('API Response:', response);
        if (response.error) {
          alert(response.error);
          this.isLoading = false;
          this.dataSource.data = [];
          this.hasChartData = false;
          return;
        }

        if (response.plot_url) {
          this.plotUrl = this.sanitizer.bypassSecurityTrustResourceUrl(response.plot_url);
        }

        const forecastData: ForecastData[] = response.dates.map((date: string, index: number) => {
          const forecastedDemand = parseInt(response.forecasted_demand[index] || 0);
          const remainingStockLevel = parseInt(response.remaining_stock_level[index] || 0);
          const openingStockLevel = parseInt(response.current_stock_level[index] || 0);
          const stockout = response.stockout[index] || false;

          if (stockout) {
            this.stockoutDates.push(date);
          }

          return {
            date,
            forecastedDemand,
            remainingStockLevel,
            openingStockLevel,
            stockout
          };
        });

        this.dataSource.data = forecastData;
        this.dataSource.paginator = this.paginator;
        this.dataSource.sort = this.sort;

        this.hasChartData = forecastData.length > 0;
        if (this.hasChartData) {
          setTimeout(() => this.renderChart(), 0);
        }

        this.isLoading = false;
      },
      error: (error) => {
        console.error('Error fetching prediction:', error);
        let errorMessage = 'Failed to fetch prediction data. Please try again later.';
        if (error.status === 0) {
          errorMessage += ` (Possible CORS or network issue. Check if the API server is running at ${this.apiBaseUrl}.)`;
        } else if (error.status) {
          errorMessage += ` (HTTP ${error.status}: ${error.statusText})`;
        }
        alert(errorMessage);
        this.isLoading = false;
        this.dataSource.data = [];
        this.hasChartData = false;
      }
    });
  }

  renderChart() {
    console.log('Attempting to render chart...');
    if (!this.forecastChart || !this.forecastChart.nativeElement) {
      console.error('Canvas element not found');
      return;
    }

    const ctx = this.forecastChart.nativeElement.getContext('2d');
    if (!ctx) {
      console.error('Could not get canvas context');
      return;
    }

    if (!this.hasChartData || this.dataSource.data.length === 0) {
      console.warn('No data available to render chart');
      return;
    }

    if (this.chart) {
      this.chart.destroy();
    }

    const forecastData = this.dataSource.data;
    const dates = forecastData.map(d => d.date);
    const demands = forecastData.map(d => parseFloat(d.forecastedDemand));
    const remainingStocks = forecastData.map(d => parseFloat(d.remainingStockLevel));
    const currentStocks = forecastData.map(d => parseFloat(d.openingStockLevel));

    const stockoutAnnotations: BoxAnnotationOptions[] = this.stockoutDates.map(date => ({
      type: 'box',
      xMin: date,
      xMax: date,
      backgroundColor: 'rgba(255, 0, 0, 0.2)',
      borderColor: 'rgba(255, 0, 0, 0.5)',
      borderWidth: 1,
      label: {
        content: 'Stock-Out',
        enabled: true,
        position: 'center'
      }
    }));

    this.chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: dates,
        datasets: [
          {
            label: 'Forecasted Demand',
            data: demands,
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            fill: false,
            tension: 0.1,
            pointRadius: 4,
            pointHoverRadius: 6
          },
          {
            label: 'Remaining Stock Level',
            data: remainingStocks,
            borderColor: '#10b981',
            backgroundColor: 'rgba(16, 185, 129, 0.1)',
            fill: false,
            tension: 0.1,
            pointRadius: 4,
            pointHoverRadius: 6
          },
          {
            label: 'Opening Stock Level',
            data: currentStocks,
            borderColor: '#f59e0b',
            backgroundColor: 'rgba(245, 158, 11, 0.1)',
            fill: false,
            tension: 0.1,
            pointRadius: 4,
            pointHoverRadius: 6
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            title: { display: true, text: 'Date' },
            ticks: { maxRotation: 45, minRotation: 45 }
          },
          y: {
            title: { display: true, text: 'Units' },
            beginAtZero: true,
            suggestedMax: Math.max(...demands, ...remainingStocks, ...currentStocks) * 1.1
          }
        },
        plugins: {
          legend: { position: 'top' },
          tooltip: { mode: 'index', intersect: false },
          annotation: {
            annotations: stockoutAnnotations
          }
        },
        interaction: { mode: 'nearest', axis: 'x', intersect: false }
      }
    });

    const chartContainer = this.forecastChart.nativeElement.parentElement;
    if (chartContainer) {
      chartContainer.classList.add('visible');
    }
  }
}