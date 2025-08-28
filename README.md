# Application Instance Dashboard

<div align="center">

## Tech Stack

<img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
<img src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Streamlit" />
<img src="https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite" />
<img src="https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white" alt="Pandas" />
<img src="https://img.shields.io/badge/Plotly-3F4F75?style=for-the-badge&logo=plotly&logoColor=white" alt="Plotly" />

</div>

A Streamlit-based dashboard for monitoring and analyzing applications across thousands of instances with automated data collection and rapid visualization capabilities.

## Overview

This dashboard provides comprehensive monitoring and analysis of application deployments across multiple instances. It processes JSON data collected from various instances to deliver insights into application status, performance metrics, and deployment patterns.

![Dashboard Screenshot](assets/Screen%20Shot%202025-08-28%20at%2006.58.44.png)

## Features

- **Application Overview**: Interactive visualizations and comprehensive metrics
- **Instance Details**: Deep dive analysis into individual instances and their applications
- **Filtered View**: Dynamic filtering and focused analysis capabilities
- **Database Table**: Complete searchable application database with export functionality
- **Real-time Data Processing**: Automated JSON data ingestion and processing
- **Export Capabilities**: Data export in multiple formats (CSV, Excel, JSON)

## Architecture

### Data Collection

The system uses a shell script (`scripts/application-collector.sh`) to gather application data from target instances. This script collects:

- Instance metadata (ID, name, script version)
- Application information (name, type, status, image, ports)
- Process details (PIDs, process names, container IDs)
- Runtime status and configuration

### Data Flow

1. **Collection**: Data is collected using the provided script
2. **Automation**: Deployment via cloud orchestration or configuration management tools
3. **Upload**: JSON files are uploaded to the dashboard
4. **Processing**: Data is processed and stored in SQLite database
5. **Visualization**: Interactive dashboard displays processed information

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd helper-data
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
streamlit run app.py
```

4. Access the dashboard at `http://localhost:8501`

## Data Collection

### Manual Collection

Execute the data collection script on target instances:

```bash
# Make script executable
chmod +x scripts/application-collector.sh

# Run collection script
./scripts/application-collector.sh
```

The script generates JSON files with the naming convention:
`{instance_id}_{instance_name}_{date}_{hour}.json`

### Automated Collection

Deploy data collection across multiple instances using automation tools:

#### AWS Systems Manager (SSM)

```bash
# Create SSM document for script execution
aws ssm create-document \
  --name "ApplicationDataCollection" \
  --document-type "Command" \
  --content file://ssm-document.json

# Execute across instance fleet
aws ssm send-command \
  --document-name "ApplicationDataCollection" \
  --targets "Key=tag:Environment,Values=production" \
  --parameters "scriptUrl=https://your-bucket/application-collector.sh"
```

#### Ansible Playbook

```yaml
---
- name: Collect Application Data
  hosts: all
  tasks:
    - name: Copy collection script
      copy:
        src: scripts/application-collector.sh
        dest: /tmp/application-collector.sh
        mode: '0755'
    
    - name: Execute data collection
      shell: /tmp/application-collector.sh
      register: collection_result
    
    - name: Fetch collected data
      fetch:
        src: "{{ collection_result.stdout_lines[-1] }}"
        dest: ./collected-data/
        flat: yes
```

#### CloudOps Orchestration Service

Configure orchestration workflows to:
1. Deploy collection scripts to target instances
2. Execute data collection on scheduled intervals
3. Aggregate collected JSON files
4. Upload data to centralized storage
5. Trigger dashboard data refresh

## Data Format

The expected JSON structure for each instance:

```json
{
  "instance_id": "i-1234567890abcdef0",
  "instance_name": "web-server-01",
  "script_version": "1.0.0",
  "applications": [
    {
      "name": "nginx",
      "type": "docker",
      "status": "running",
      "image": "nginx:latest",
      "ports": [80, 443],
      "pids": [1234, 5678],
      "process_name": "nginx",
      "container_id": "abc123def456"
    }
  ]
}
```

## Usage

### Data Upload

1. Navigate to the dashboard homepage
2. Use the file upload section to select JSON files
3. Upload single files or multiple files simultaneously
4. Data is automatically processed and stored

### Navigation

- **Overview**: View application distribution, status summaries, and key metrics
- **Instance Details**: Analyze specific instances and their application portfolios
- **Filtered View**: Apply filters to focus on specific subsets of data
- **Database Table**: Access complete dataset with search and export capabilities

### Data Export

Export filtered data in multiple formats:
- CSV for spreadsheet analysis
- Excel for advanced reporting
- JSON for programmatic processing

## Database

The application uses SQLite for data persistence:
- Database file: `dashboard_data.db`
- Automatic schema creation and migration
- Optimized queries for dashboard performance

## Configuration

### Environment Variables

- `STREAMLIT_SERVER_PORT`: Dashboard port (default: 8501)
- `DATABASE_PATH`: SQLite database location

### Customization

Modify `app.py` to:
- Add custom metrics and visualizations
- Implement additional data sources
- Extend filtering capabilities
- Customize export formats

## Performance Considerations

- Optimized for datasets with thousands of instances
- Efficient data processing and caching
- Responsive UI with progressive loading
- Database indexing for fast queries

## Troubleshooting

### Common Issues

1. **File Upload Errors**: Verify JSON format and file permissions
2. **Database Errors**: Check SQLite file permissions and disk space
3. **Performance Issues**: Consider data volume and available system resources

### Logs

Monitor application logs for:
- Data processing errors
- Database connection issues
- File upload problems

## Contributing

1. Fork the repository
2. Create feature branch
3. Implement changes with tests
4. Submit pull request with detailed description

## License

This project is licensed under the MIT License. See LICENSE file for details.
