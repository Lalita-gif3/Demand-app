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
import annotationPlugin, { AnnotationOptions } from 'chartjs-plugin-annotation';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

// Register annotation plugin globally
Chart.register(annotationPlugin);

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
  selectedProductId: string = '';
  startDate: string = this.getDefaultStartDate();
  endDate: string = this.getDefaultEndDate();
  stockoutDates: string[] = [];
  isLoading: boolean = false;
  mae: number | null = null;

  hasChartData: boolean = false;

  displayedColumns: string[] = [
    'date',
    'openingStockLevel',
    'forecastedDemand',
    'remainingStockLevel',
    'stockout'
  ];

  dataSource = new MatTableDataSource<ForecastData>([]);

  @ViewChild('forecastChart') forecastChart!: ElementRef<HTMLCanvasElement>;
  @ViewChild(MatPaginator) paginator!: MatPaginator;
  @ViewChild(MatSort) sort!: MatSort;
  chart: Chart | undefined;

  private apiBaseUrl: string = 'http://20.174.3.84:8000';

  constructor(private http: HttpClient) {}

  ngOnInit() {
    this.fetchProductIds();
  }

  private getDefaultStartDate(): string {
    const date = new Date();
    date.setDate(date.getDate() + 1);
    return date.toISOString().split('T')[0];
  }

  private getDefaultEndDate(): string {
    const date = new Date();
    date.setDate(date.getDate() + 8);
    return date.toISOString().split('T')[0];
  }

  private fetchProductIds() {
    this.http.get<string[]>(`${this.apiBaseUrl}/products`).subscribe({
      next: (data) => {
        this.productIds = data;
        if (this.productIds.length > 0) {
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
    this.hasChartData = false;
    this.mae = null;

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
        console.log('API response:', response);
        if (response.error) {
          alert(response.error);
          this.isLoading = false;
          return;
        }

        const forecastData: ForecastData[] = response.dates.map((date: string, index: number) => {
          const dataPoint: ForecastData = {
            date: date,
            forecastedDemand: response.forecasted_demand[index],
            remainingStockLevel: response.remaining_stock_level[index],
            openingStockLevel: response.current_stock_level[index],
            stockout: response.stockout[index]
          };

          if (dataPoint.stockout) {
            this.stockoutDates.push(date);
          }

          return dataPoint;
        });

        this.dataSource.data = forecastData;
        this.hasChartData = forecastData.length > 0;
        this.mae = response.mae;

        setTimeout(() => {
          this.renderChart();
          this.isLoading = false;
        }, 100);
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
      }
    });
  }

  renderChart() {
    console.log('Attempting to render chart...');
    
    if (!this.forecastChart?.nativeElement) {
      console.error('Canvas element not found');
      return;
    }

    const ctx = this.forecastChart.nativeElement.getContext('2d');
    if (!ctx) {
      console.error('Could not get 2D context');
      return;
    }

    // Destroy existing chart if exists
    if (this.chart) {
      this.chart.destroy();
    }

    const forecastData = this.dataSource.data;
    if (forecastData.length === 0) {
      console.warn('No data available to render chart');
      return;
    }

    const dates = forecastData.map(d => d.date);
    const demands = forecastData.map(d => d.forecastedDemand);
    const remainingStocks = forecastData.map(d => d.remainingStockLevel);
    const currentStocks = forecastData.map(d => d.openingStockLevel);

    console.log('Chart data:', {
      dates,
      demands,
      remainingStocks,
      currentStocks
    });

    // Create stockout regions data
    const stockoutRegions: {start: number, end: number}[] = [];
    let inStockout = false;
    let startIndex = -1;
    
    for (let i = 0; i < forecastData.length; i++) {
      if (forecastData[i].stockout && !inStockout) {
        // Start of a stockout period
        inStockout = true;
        startIndex = i;
      } else if (!forecastData[i].stockout && inStockout) {
        // End of a stockout period
        inStockout = false;
        stockoutRegions.push({
          start: startIndex,
          end: i - 1
        });
      }
    }
    
    // Handle case where stockout continues to the end
    if (inStockout) {
      stockoutRegions.push({
        start: startIndex,
        end: forecastData.length - 1
      });
    }

    // Create annotations for stockout regions
    const stockoutAnnotations: AnnotationOptions[] = stockoutRegions.map(region => ({
      type: 'box',
      xMin: dates[region.start],
      xMax: dates[region.end],
      backgroundColor: 'rgba(255, 99, 132, 0.2)',
      borderColor: 'rgba(255, 99, 132, 0.5)',
      borderWidth: 1,
      label: {
        content: 'Stockout Risk',
        display: true,
        position: 'center',
        backgroundColor: 'rgba(255, 99, 132, 0.8)',
        color: 'white',
        font: {
          size: 12,
          weight: 'bold'
        }
      }
    }));

    console.log('Stockout annotations:', stockoutAnnotations);

    try {
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
              label: 'Opening Stock Level',
              data: currentStocks,
              borderColor: '#f59e0b',
              backgroundColor: 'rgba(245, 158, 11, 0.1)',
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
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: {
              type: 'category',
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
            tooltip: { 
              mode: 'index', 
              intersect: false,
              callbacks: {
                label: function(context) {
                  let label = context.dataset.label || '';
                  if (label) {
                    label += ': ';
                  }
                  if (context.parsed.y !== null) {
                    label += context.parsed.y;
                  }
                  return label;
                }
              }
            },
            annotation: {
              annotations: stockoutAnnotations as any
            }
          }
        }
      });
      console.log('Chart created successfully');
    } catch (error) {
      console.error('Error creating chart:', error);
    }
  }
}

interface ForecastData {
  date: string;
  forecastedDemand: number;
  remainingStockLevel: number;
  openingStockLevel: number;
  stockout: boolean;
}