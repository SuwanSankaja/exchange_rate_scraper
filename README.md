# 🚀 GitHub Workflow-Friendly Foreign Currency Exchange Rate Scraper

This enhanced version of the exchange rate scraper is optimized for automated execution in GitHub Actions with comprehensive logging, error handling, and debugging capabilities.

## 📁 File Structure

```
your-repo/
├── .github/
│   └── workflows/
│       └── daily-scraper.yml          # GitHub workflow file
├── daily_aud_rate_scraper.py           # Main scraper script (workflow-optimized)
├── requirements.txt                   # Python dependencies
├── .env.example                      # Environment variables template
├── logs/                             # Created automatically for log files
├── screenshots/                      # Created automatically for debugging screenshots
└── README.md                         # This file
```

## 🔧 Setup Instructions

### 1. Repository Setup

1. Copy the workflow-optimized script to `daily_aud_rate_scraper.py`
2. Copy the workflow file to `.github/workflows/daily-scraper.yml`
3. Copy `requirements.txt` to your repository root

### 2. MongoDB Atlas Secret

Add your MongoDB connection string as a repository secret:

1. Go to your repository → Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Name: `MONGODB_CONNECTION_STRING`
4. Value: Your MongoDB Atlas connection string (e.g., `mongodb+srv://username:password@cluster.mongodb.net/`)

### 3. Environment Variables (Optional)

Create a `.env` file for local testing:

```env
MONGODB_CONNECTION_STRING=your_mongodb_atlas_connection_string_here
TZ=Asia/Colombo
```

## 🎯 Key Features

### ✨ **Workflow Optimizations**

- **Enhanced Logging**: Comprehensive logging for GitHub Actions with timestamped log files
- **Screenshot Capture**: Automatic screenshots for debugging Selenium issues
- **Environment Detection**: Automatically detects GitHub Actions environment
- **Error Handling**: Graceful error handling with detailed error messages
- **Execution Summary**: JSON summary of execution results for artifacts

### 🛠️ **Debugging Features**

- **Log Files**: Timestamped log files saved to `logs/` directory
- **Screenshots**: Debug screenshots saved to `screenshots/` directory
- **Execution Summary**: JSON file with execution details
- **Chrome/Selenium Testing**: Pre-flight checks for browser setup
- **Artifact Upload**: Automatic upload of logs and screenshots on failure

### 📊 **Data Sources**

1. **Primary**: numbers.lk (multiple banks at once)
2. **Enhanced**: Direct NTB scraping for verification/backup
3. **Fallback**: Multiple Selenium strategies for robust data collection

## 🚀 Usage

### Automated Execution

The workflow runs automatically at **10:00 AM Sri Lanka Time** daily via cron schedule.

### Manual Execution

You can manually trigger the workflow:

1. Go to your repository → Actions
2. Select "Daily AUD Exchange Rate Scraper"
3. Click "Run workflow"
4. Optional: Enable debug mode for extended logging

### Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export MONGODB_CONNECTION_STRING="your_connection_string"

# Run the scraper
python daily_aud_rate_scraper.py
```

## 📋 Workflow Steps

1. **Environment Setup**: Install Chrome, Python dependencies
2. **System Verification**: Test Chrome and Selenium configuration
3. **Data Scraping**: Execute the enhanced scraper
4. **Results Processing**: Generate execution summary
5. **Artifact Upload**: Save logs, screenshots, and summary

## 🔍 Monitoring & Debugging

### Success Indicators

- ✅ Green workflow badge
- 📊 Execution summary with bank count
- 🏦 MongoDB data successfully updated

### Troubleshooting

If the workflow fails:

1. **Check Artifacts**: Download failure logs and screenshots
2. **Review Logs**: Look for specific error messages
3. **Common Issues**:
   - MongoDB connection problems → Check secret configuration
   - Website changes → Review scraping logic
   - Chrome/Selenium issues → Check browser setup
   - Network problems → Retry or investigate connectivity

### Log Files

- `logs/exchange_scraper_YYYYMMDD_HHMMSS.log`: Main execution log
- `screenshots/`: Debug screenshots if Selenium fails
- `execution_summary.json`: Summary of execution results

## 🎛️ Configuration Options

### Workflow Inputs

- `debug_mode`: Enable extended logging and debugging features

### Environment Variables

- `MONGODB_CONNECTION_STRING`: MongoDB Atlas connection string (required)
- `TZ`: Timezone (default: Asia/Colombo)
- `PYTHONUNBUFFERED`: Ensures real-time log output

## 📈 Expected Outputs

### Successful Execution

```
✅ Exchange rate scraper completed successfully
📊 Successfully scraped data from 9 banks
🏦 Banks: Central Bank of Sri Lanka, Amana Bank, Bank of Ceylon, Commercial Bank, Hatton National Bank, HSBC Bank, Nations Trust Bank, People's Bank, Sampath Bank
```

### Execution Summary JSON

```json
{
  "execution_time": "2024-01-15T10:30:00",
  "total_banks_scraped": 9,
  "banks_list": ["Central Bank of Sri Lanka", "Amana Bank", ...],
  "sources_used": ["numbers.lk", "NTB Direct"],
  "best_rate_to_sell_aud": {
    "bank": "Bank of Ceylon",
    "rate": 189.50
  },
  "best_rate_to_buy_aud": {
    "bank": "Commercial Bank",
    "rate": 192.00
  }
}
```

## 🔒 Security Considerations

- MongoDB connection string is stored as an encrypted repository secret
- No sensitive data is logged or exposed in artifacts
- Screenshots may contain web page content but no credentials

## 🚨 Error Handling

The scraper includes comprehensive error handling for:

- Network connectivity issues
- MongoDB connection failures
- Selenium/Chrome configuration problems
- Website structure changes
- Rate limit or blocking scenarios

All errors are logged with detailed context for troubleshooting.
