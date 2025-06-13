using System;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using CsvHelper;
using CsvHelper.Configuration;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.AspNetCore.Http;
using System.Globalization;
using System.IO;
using System.Collections.Generic;
using System.Text.RegularExpressions;

public record PredictionRequest(string product_id, string start_date, string end_date);

public class StockRecord
{
    public string? product_id { get; set; }
    public string? Date { get; set; }
    public string? Current_Stock_Level { get; set; }
}

public sealed class StockRecordMap : ClassMap<StockRecord>
{
    public StockRecordMap()
    {
        Map(m => m.product_id).Name("product_id");
        Map(m => m.Date).Name("Date");
        Map(m => m.Current_Stock_Level).Name("Opening Stock Level");
    }
}

class Program
{
    // Helper method to reformat dates in a JSON object to exclude time
    private static object FormatDatesInObject(object obj)
    {
        if (obj == null)
            return null;

        if (obj is string stringValue)
        {
            // Try to parse the string as a DateTime
            if (DateTime.TryParse(stringValue, CultureInfo.InvariantCulture, DateTimeStyles.None, out var date))
            {
                return date.ToString("yyyy-MM-dd");
            }
            return stringValue;
        }
        else if (obj is IDictionary<string, object> dict)
        {
            var newDict = new Dictionary<string, object>();
            foreach (var kvp in dict)
            {
                newDict[kvp.Key] = FormatDatesInObject(kvp.Value);
            }
            return newDict;
        }
        else if (obj is IList<object> list)
        {
            return list.Select(FormatDatesInObject).ToList();
        }
        else if (obj is IEnumerable<object> enumerable && !(obj is string))
        {
            return enumerable.Select(FormatDatesInObject).ToList();
        }

        return obj;
    }

    static async Task Main(string[] args)
    {
        var builder = WebApplication.CreateBuilder(args);

        // Add HttpClient and configuration services
        builder.Services.AddHttpClient();

        // Cache product IDs at startup
        builder.Services.AddSingleton<HashSet<string>>(provider =>
        {
            var csvPath = builder.Configuration["DataPaths:CleanedDataset"]
                ?? "/mnt/c/Users/lalit/OneDrive/Desktop/demand stockout app/cleaned_dataset.csv";
            var productIds = new HashSet<string>();
            try
            {
                using (var reader = new StreamReader(csvPath))
                using (var csv = new CsvReader(reader, CultureInfo.InvariantCulture))
                {
                    var records = csv.GetRecords<dynamic>();
                    foreach (var record in records)
                    {
                        if (record.product_id != null)
                            productIds.Add(record.product_id.ToString().Trim());
                    }
                }
                Console.WriteLine($"✅ Loaded {productIds.Count} product IDs");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"⛔ Error loading product IDs: {ex.Message}");
            }
            return productIds;
        });

        // Configure CORS for Angular
        builder.Services.AddCors(options =>
        {
            options.AddPolicy("AllowAngular", builder =>
            {
                builder.WithOrigins("http://localhost:4200")
                       .AllowAnyMethod()
                       .AllowAnyHeader();
            });
        });

        var app = builder.Build();
        app.UseCors("AllowAngular");

        // Endpoint to get unique product IDs
        app.MapGet("/api/prediction/product-ids", (HashSet<string> productIds) =>
        {
            if (!productIds.Any())
                return Results.Problem("No product IDs available");
            return Results.Ok(productIds.OrderBy(id => id).ToList());
        });

        // Endpoint to fetch Opening Stock Level
        app.MapGet("/api/prediction/current-stock/{productId}", (string productId, IConfiguration configuration, HashSet<string> productIds) =>
        {
            if (string.IsNullOrWhiteSpace(productId))
                return Results.BadRequest("Product ID cannot be empty");

            var normalizedProductId = productId.Trim();
            if (!productIds.Contains(normalizedProductId))
                return Results.NotFound(new { message = $"Product ID {productId} not found in dataset" });

            var csvPath = configuration["DataPaths:CleanedDataset"]
                ?? "/mnt/c/Users/lalit/OneDrive/Desktop/demand stockout app/cleaned_dataset.csv";

            if (!File.Exists(csvPath))
                return Results.Problem($"CSV file not found at path: {csvPath}");

            try
            {
                using (var reader = new StreamReader(csvPath))
                using (var csv = new CsvReader(reader, CultureInfo.InvariantCulture))
                {
                    csv.Context.RegisterClassMap<StockRecordMap>();

                    var records = csv.GetRecords<StockRecord>()
                        .Where(record =>
                            record.product_id != null &&
                            record.product_id.Trim().Equals(normalizedProductId, StringComparison.OrdinalIgnoreCase))
                        .ToList();

                    if (!records.Any())
                        return Results.NotFound(new { message = $"No stock data found for product {productId}" });

                    var parsedRecords = new List<(DateTime Date, double StockLevel)>();

                    foreach (var record in records)
                    {
                        // Parse stock level
                        double stockLevel = 0;
                        var rawValue = record.Current_Stock_Level?.Trim();

                        if (!string.IsNullOrWhiteSpace(rawValue))
                        {
                            // Enhanced cleaning: handle commas, negative signs, and decimals
                            var cleanedValue = Regex.Replace(rawValue, @"[^\d.-]", "");
                            if (!double.TryParse(cleanedValue, NumberStyles.Any, CultureInfo.InvariantCulture, out stockLevel))
                            {
                                Console.WriteLine($"❌ Failed to parse stock level: {rawValue} (Cleaned: {cleanedValue})");
                                continue;
                            }
                        }
                        else
                        {
                            Console.WriteLine($"⚠️ Empty or null stock level for date: {record.Date}");
                        }

                        // Parse date
                        if (DateTime.TryParseExact(record.Date, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var recordDate))
                        {
                            parsedRecords.Add((recordDate, stockLevel));
                        }
                        else
                        {
                            Console.WriteLine($"⚠️ Skipped record - Invalid date format: {record.Date}");
                            continue;
                        }
                    }

                    if (!parsedRecords.Any())
                        return Results.NotFound(new { message = $"No valid records found for product {productId} after parsing" });

                    // Order by date (newest first)
                    var orderedRecords = parsedRecords.OrderByDescending(x => x.Date).ToList();

                    // Debug: Print all records
                    Console.WriteLine($"\n📊 All records for {productId}:");
                    foreach (var rec in orderedRecords)
                    {
                        Console.WriteLine($"{rec.Date:yyyy-MM-dd} | Stock: {rec.StockLevel}");
                    }

                    // Find most recent non-zero stock
                    var nonZeroRecord = orderedRecords.FirstOrDefault(x => x.StockLevel > 0);

                    if (nonZeroRecord != default)
                    {
                        Console.WriteLine($"\n🔥 Using NON-ZERO record: {nonZeroRecord.Date:yyyy-MM-dd} | Stock: {nonZeroRecord.StockLevel}");
                        return Results.Ok(new
                        {
                            openingStockLevel = nonZeroRecord.StockLevel,
                            Date = nonZeroRecord.Date.ToString("yyyy-MM-dd"),
                            IsMostRecentNonZero = true
                        });
                    }

                    // Fallback to most recent record
                    var mostRecent = orderedRecords.First();
                    Console.WriteLine($"\n⚠️ Using MOST RECENT record (zero stock): {mostRecent.Date:yyyy-MM-dd} | Stock: {mostRecent.StockLevel}");
                    return Results.Ok(new
                    {
                        openingStockLevel = mostRecent.StockLevel,
                        Date = mostRecent.Date.ToString("yyyy-MM-dd"),
                        IsMostRecentNonZero = false,
                        Warning = "All stock levels are zero or no non-zero stock found"
                    });
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"⛔ Error: {ex.Message}\n{ex.StackTrace}");
                return Results.Problem($"Error fetching stock: {ex.Message}");
            }
        });

        // Endpoint to fetch stock history for visualization
        app.MapGet("/api/prediction/stock-history/{productId}", (string productId, IConfiguration configuration, HashSet<string> productIds) =>
        {
            if (string.IsNullOrWhiteSpace(productId))
                return Results.BadRequest("Product ID cannot be empty");

            var normalizedProductId = productId.Trim();
            if (!productIds.Contains(normalizedProductId))
                return Results.NotFound(new { message = $"Product ID {productId} not found in dataset" });

            var csvPath = configuration["DataPaths:CleanedDataset"]
                ?? "/mnt/c/Users/lalit/OneDrive/Desktop/demand stockout app/cleaned_dataset.csv";

            if (!File.Exists(csvPath))
                return Results.Problem($"CSV file not found at path: {csvPath}");

            try
            {
                using (var reader = new StreamReader(csvPath))
                using (var csv = new CsvReader(reader, CultureInfo.InvariantCulture))
                {
                    csv.Context.RegisterClassMap<StockRecordMap>();

                    var records = csv.GetRecords<StockRecord>()
                        .Where(record =>
                            record.product_id != null &&
                            record.product_id.Trim().Equals(normalizedProductId, StringComparison.OrdinalIgnoreCase))
                        .ToList();

                    if (!records.Any())
                        return Results.NotFound(new { message = $"No stock data found for product {productId}" });

                    var parsedRecords = new List<(DateTime Date, double StockLevel)>();

                    foreach (var record in records)
                    {
                        double stockLevel = 0;
                        var rawValue = record.Current_Stock_Level?.Trim();

                        if (!string.IsNullOrWhiteSpace(rawValue))
                        {
                            var cleanedValue = Regex.Replace(rawValue, @"[^\d.-]", "");
                            if (!double.TryParse(cleanedValue, NumberStyles.Any, CultureInfo.InvariantCulture, out stockLevel))
                                continue;
                        }

                        if (DateTime.TryParseExact(record.Date, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var recordDate))
                        {
                            parsedRecords.Add((recordDate, stockLevel));
                        }
                    }

                    if (!parsedRecords.Any())
                        return Results.NotFound(new { message = $"No valid records found for product {productId}" });

                    var orderedRecords = parsedRecords.OrderBy(x => x.Date).ToList();

                    // Create a line chart
                    return Results.Ok(new
                    {
                        Chart = new
                        {
                            Type = "line",
                            Data = new
                            {
                                Labels = orderedRecords.Select(r => r.Date.ToString("yyyy-MM-dd")).ToArray(),
                                Datasets = new[]
                                {
                                    new
                                    {
                                        Label = "Stock Level",
                                        Data = orderedRecords.Select(r => r.StockLevel).ToArray(),
                                        BorderColor = "#4CAF50",
                                        BackgroundColor = "#4CAF50",
                                        Fill = false,
                                        Tension = 0.1
                                    }
                                }
                            },
                            Options = new
                            {
                                Scales = new
                                {
                                    X = new { Title = new { Display = true, Text = "Date" } },
                                    Y = new { Title = new { Display = true, Text = "Stock Level" } }
                                },
                                Plugins = new { Title = new { Display = true, Text = $"Stock History for {productId}" } }
                            }
                        }
                    });
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"⛔ Error: {ex.Message}\n{ex.StackTrace}");
                return Results.Problem($"Error fetching stock history: {ex.Message}");
            }
        });

        // Proxy prediction request to FastAPI
        app.MapPost("/api/prediction/predict", async (HttpContext context, HttpClient httpClient, IConfiguration configuration) =>
        {
            var requestBody = await context.Request.ReadFromJsonAsync<PredictionRequest>();
            if (requestBody == null)
                return Results.BadRequest("Invalid request body");

            var fastApiUrl = configuration["FastApi:Url"] ?? "http://localhost:8000/predict";
            var jsonContent = new StringContent(
                JsonSerializer.Serialize(requestBody),
                Encoding.UTF8,
                "application/json"
            );

            try
            {
                var response = await httpClient.PostAsync(fastApiUrl, jsonContent);
                response.EnsureSuccessStatusCode();
                var responseContent = await response.Content.ReadAsStringAsync();
                var deserializedResponse = JsonSerializer.Deserialize<object>(responseContent);
                // Reformat dates in the response to exclude time
                var formattedResponse = FormatDatesInObject(deserializedResponse);
                return Results.Ok(formattedResponse);
            }
            catch (HttpRequestException ex)
            {
                Console.WriteLine($"⛔ FastAPI error: {ex.Message}");
                return Results.Problem($"FastAPI service unavailable: {ex.Message}");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"⛔ Error: {ex.Message}\n{ex.StackTrace}");
                return Results.Problem($"Error processing prediction: {ex.Message}");
            }
        });

        await app.RunAsync();
    }
}