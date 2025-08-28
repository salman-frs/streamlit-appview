import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.figure_factory as ff
import json
from typing import Dict, List, Any
import io
import numpy as np
from datetime import datetime, timedelta
import sqlite3
import os
try:
    import openpyxl
except ImportError:
    st.warning("⚠️ openpyxl not installed. Excel export will not be available. Install with: pip install openpyxl")
    openpyxl = None

# Streamlit page configuration
st.set_page_config(
    page_title="Instance Application Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Disable auto-refresh for static data
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False

# Initialize session state for navigation
if 'current_page' not in st.session_state:
    st.session_state.current_page = 'overview'
if 'selected_filter' not in st.session_state:
    st.session_state.selected_filter = {}
if 'processing_errors' not in st.session_state:
    st.session_state.processing_errors = []

# Initialize download button counter for unique keys
if 'download_button_counter' not in st.session_state:
    st.session_state.download_button_counter = 0

def get_unique_download_key(prefix: str) -> str:
    """Generate a unique key for download buttons"""
    import random
    st.session_state.download_button_counter += 1
    # Include current page context, counter, timestamp, and random number for absolute uniqueness
    page_context = getattr(st.session_state, 'current_page', 'default')
    timestamp = datetime.now().strftime('%H%M%S%f')
    random_id = random.randint(10000, 99999)
    return f"{page_context}_{prefix}_{st.session_state.download_button_counter}_{timestamp}_{random_id}"

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.8rem;
        font-weight: bold;
        color: #2c3e50;
        text-align: center;
        margin-bottom: 1rem;
        padding: 1rem;
        background: linear-gradient(90deg, #3498db, #2980b9);
        color: white;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .subtitle {
        font-size: 1.2rem;
        color: #7f8c8d;
        text-align: center;
        margin-bottom: 2rem;
        font-style: italic;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 5px solid #3498db;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        margin-bottom: 1rem;
    }
    .stDataFrame {
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    }
    .critical-service-alert {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
    }
    .nav-button {
        background-color: #3498db;
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 5px;
        cursor: pointer;
        margin: 0.2rem;
    }
    .nav-button:hover {
        background-color: #2980b9;
    }
    .error-notification {
        position: fixed;
        top: 20px;
        right: 20px;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 5px;
        padding: 0.5rem;
        z-index: 1000;
        cursor: pointer;
    }
    .page-container {
        padding: 1rem;
        margin-top: 1rem;
    }
</style>
""", unsafe_allow_html=True)

def show_error_notification():
    """Show error notification icon with expandable details"""
    if st.session_state.processing_errors:
        with st.container():
            col1, col2 = st.columns([10, 1])
            with col2:
                if st.button("⚠️", help=f"{len(st.session_state.processing_errors)} error(s) occurred"):
                    with st.expander("Processing Errors", expanded=True):
                        for error in st.session_state.processing_errors:
                            st.error(error)
                        if st.button("Clear Errors"):
                            st.session_state.processing_errors = []
                            st.rerun()

def navigate_to_page(page_name, filter_data=None):
    """Navigate to a specific page with optional filter"""
    st.session_state.current_page = page_name
    if filter_data:
        st.session_state.selected_filter = filter_data
    st.rerun()

def create_navigation_bar():
    """Create navigation bar for different pages"""
    st.markdown("### 🧭 Navigation")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("📊 Application Overview", width='stretch'):
            navigate_to_page('overview')
    
    with col2:
        if st.button("🏢 Instance Details", width='stretch'):
            navigate_to_page('instance_details')
    
    with col3:
        if st.button("🔍 Filtered View", width='stretch'):
            navigate_to_page('filtered_view')
    
    with col4:
        if st.button("📋 Database Table", width='stretch'):
            navigate_to_page('data_table')
    
    st.markdown("---")

def load_and_validate_json(uploaded_file) -> Dict[str, Any]:
    """
    Load and validate JSON file structure.
    
    Args:
        uploaded_file: Streamlit uploaded file object
        
    Returns:
        Dict containing the parsed JSON data
        
    Raises:
        ValueError: If JSON structure is invalid
    """
    try:
        content = uploaded_file.read()
        if len(content) == 0:
            raise ValueError("File is empty")
            
        data = json.loads(content)
        
        # Basic validation
        required_fields = ['instance_id', 'instance_name', 'applications']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
        
        # Validate field types
        if not isinstance(data['instance_id'], str) or not data['instance_id'].strip():
            raise ValueError("'instance_id' must be a non-empty string")
            
        if not isinstance(data['instance_name'], str) or not data['instance_name'].strip():
            raise ValueError("'instance_name' must be a non-empty string")
        
        if not isinstance(data['applications'], list):
            raise ValueError("'applications' must be a list")
            
        # Validate applications structure
        if len(data['applications']) == 0:
            raise ValueError("'applications' list is empty")
            
        for i, app in enumerate(data['applications']):
            if not isinstance(app, dict):
                raise ValueError(f"Application {i+1} must be an object")
            if 'name' not in app:
                raise ValueError(f"Application {i+1} missing 'name' field")
                
        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format at line {e.lineno}: {e.msg}")
    except Exception as e:
        raise ValueError(f"Error processing file: {str(e)}")

@st.cache_data(ttl=3600)  # Cache for 1 hour since data is static
def process_instance_data(uploaded_files):
    """
    Process multiple uploaded files and return a combined pandas DataFrame with caching
    """
    all_dataframes = []
    
    for uploaded_file in uploaded_files:
        try:
            # Load and validate JSON
            data = load_and_validate_json(uploaded_file)
            
            # Extract instance information
            instance_id = data.get('instance_id', 'Unknown')
            instance_name = data.get('instance_name', 'Unknown')
            script_version = data.get('script_version', 'Unknown')
            
            # Process applications
            applications = data.get('applications', [])
            
            if not applications:
                st.session_state.processing_errors.append(
                    f"Error processing {uploaded_file.name}: Error processing file: 'applications' list is empty"
                )
                continue
            
            app_data = []
            for app in applications:
                app_info = {
                    'instance_id': instance_id,
                    'instance_name': instance_name,
                    'script_version': script_version,
                    'app_name': app.get('name', 'Unknown'),
                    'app_type': app.get('type', 'Unknown'),
                    'app_status': app.get('status', 'Unknown'),
                    'app_image': app.get('image', ''),
                    'ports': ', '.join(map(str, app.get('ports', []))),
                    'pids': ', '.join(map(str, app.get('pids', []))),
                    'process_name': app.get('process_name', ''),
                    'container_id': app.get('container_id', '')
                }
                app_data.append(app_info)
            
            if app_data:
                df = pd.DataFrame(app_data)
                all_dataframes.append(df)
                
        except Exception as e:
            st.session_state.processing_errors.append(
                f"Error processing {uploaded_file.name}: {str(e)}"
            )
            continue
    
    # Combine all dataframes
    if all_dataframes:
        return pd.concat(all_dataframes, ignore_index=True)
    else:
        return pd.DataFrame()

def create_summary_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate summary metrics from the processed data.
    
    Args:
        df: Processed DataFrame
        
    Returns:
        Dictionary containing summary metrics
    """
    # Calculate port statistics
    all_ports = []
    for ports_str in df['ports'].dropna():
        if ports_str:
            all_ports.extend([p.strip() for p in str(ports_str).split(',') if p.strip()])
    
    return {
        'total_instances': df['instance_id'].nunique(),
        'total_applications': len(df),
        'unique_app_types': df['app_type'].nunique(),
        'avg_apps_per_instance': round(len(df) / df['instance_id'].nunique(), 1) if df['instance_id'].nunique() > 0 else 0,
        'app_types': df['app_type'].value_counts().to_dict()
    }

def create_application_overview_page(df: pd.DataFrame):
    """
    Create the main Application Overview page with interactive visualizations
    """
    st.markdown("<div class='page-container'>", unsafe_allow_html=True)
    st.markdown("# 📊 Application Overview")
    st.markdown("Comprehensive overview of all applications across instances")
    
    if df.empty:
        st.warning("No data available for visualization.")
        return
    
    # Summary metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_instances = df['instance_id'].nunique()
        st.metric("Total Instances", total_instances)
    
    with col2:
        total_apps = len(df)
        st.metric("Total Applications", total_apps)
    
    with col3:
        app_types = df['app_type'].nunique()
        st.metric("App Types", app_types)
    
    with col4:
        avg_apps = round(total_apps / total_instances, 1) if total_instances > 0 else 0
        st.metric("Avg Apps/Instance", avg_apps)
    
    st.markdown("---")
    
    # Quick Actions Section
    st.markdown("### ⚡ Quick Actions")
    action_col1, action_col2, action_col3, action_col4 = st.columns(4)
    
    with action_col1:
        if st.button("🔍 View All Data", key="view_all_data_btn", help="Go to complete database table"):
            st.session_state.current_page = 'data_table'
            st.rerun()
    
    with action_col2:
        if st.button("🏢 Instance Analysis", key="instance_analysis_btn", help="Detailed instance analysis"):
            st.session_state.current_page = 'instance_details'
            st.rerun()
    
    with action_col3:
        # Find most used app type for quick filter
        most_used_app_type = df['app_type'].value_counts().index[0] if not df['app_type'].value_counts().empty else None
        if most_used_app_type and st.button(f"🎯 View {most_used_app_type}", key="view_most_used_app_btn", help=f"Filter by {most_used_app_type} applications"):
            st.session_state.current_page = 'filtered_view'
            st.session_state.selected_filter = {'type': 'app_type', 'value': most_used_app_type}
            st.rerun()
    
    with action_col4:
        # Find instance with most apps for quick access
        busiest_instance = df.groupby('instance_name').size().idxmax() if not df.empty else None
        if busiest_instance and st.button(f"🏆 Busiest Instance", key="busiest_instance_btn", help=f"View {busiest_instance} (most applications)"):
            st.session_state.current_page = 'filtered_view'
            st.session_state.selected_filter = {'type': 'instance', 'value': busiest_instance}
            st.rerun()
    
    st.markdown("---")
    
    # Interactive visualizations
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🎯 Application Types Distribution")
        app_type_counts = df['app_type'].value_counts()
        
        fig_pie = px.pie(
            values=app_type_counts.values,
            names=app_type_counts.index,
            title="Click on a segment to filter applications",
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
        fig_pie.update_layout(showlegend=True, height=400)
        
        # Display pie chart (static - no real-time interaction)
        st.plotly_chart(fig_pie, width='stretch', key="app_type_pie")
        
        # Add manual filter buttons below chart
        st.markdown("**Filter by Application Type:**")
        app_types = df['app_type'].value_counts().index.tolist()
        
        # Map application types to appropriate icons
        def get_app_type_icon(app_type):
            icon_map = {
                'docker': '🐳',
                'systemd': '⚙️',
                'service': '🔧',
                'process': '⚡',
                'container': '📦',
                'daemon': '👹',
                'application': '💻',
                'web': '🌐',
                'database': '🗄️',
                'api': '🔌',
                'server': '🖥️',
                'nginx': '🌐',
                'apache': '🌐',
                'mysql': '🗄️',
                'postgresql': '🐘',
                'redis': '🔴',
                'mongodb': '🍃'
            }
            # Check for exact match first
            if app_type.lower() in icon_map:
                return icon_map[app_type.lower()]
            # Check for partial matches
            for key, icon in icon_map.items():
                if key in app_type.lower():
                    return icon
            # Default icon for unknown types
            return '📋'
        
        filter_cols = st.columns(min(len(app_types), 4))
        for i, app_type in enumerate(app_types[:4]):
            with filter_cols[i % 4]:
                icon = get_app_type_icon(app_type)
                if st.button(f"{icon} {app_type}", key=f"filter_app_{i}", help=f"Filter by {app_type}"):
                    st.session_state.current_page = 'filtered_view'
                    st.session_state.selected_filter = {'type': 'app_type', 'value': app_type}
                    st.rerun()
    
    with col2:
        st.markdown("### 🏢 Applications per Instance")
        instance_app_counts = df.groupby('instance_name').size().reset_index(name='app_count')
        
        fig_bar = px.bar(
            instance_app_counts,
            x='instance_name',
            y='app_count',
            title="Click on a bar to view instance details",
            color='app_count',
            color_continuous_scale='Blues'
        )
        fig_bar.update_layout(height=400, xaxis_tickangle=-45)
        
        # Display bar chart (static - no real-time interaction)
        st.plotly_chart(fig_bar, width='stretch', key="instance_bar")
        
        # Add manual filter buttons below chart
        st.markdown("**Filter by Instance:**")
        top_instances = instance_app_counts.nlargest(4, 'app_count')['instance_name'].tolist()
        instance_cols = st.columns(min(len(top_instances), 4))
        for i, instance in enumerate(top_instances):
            with instance_cols[i % 4]:
                if st.button(f"🏢 {instance}", key=f"filter_instance_{i}", help=f"Filter by {instance}"):
                    st.session_state.current_page = 'filtered_view'
                    st.session_state.selected_filter = {'type': 'instance', 'value': instance}
                    st.rerun()
    
    # Additional visualizations
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🏗️ Application Architecture Overview")
        if 'app_type' in df.columns:
            # Show application architecture distribution instead of status
            arch_counts = df['app_type'].value_counts()
            fig_arch = px.bar(
                x=arch_counts.index,
                y=arch_counts.values,
                title="Application Architecture Distribution",
                color=arch_counts.values,
                color_continuous_scale='Viridis'
            )
            fig_arch.update_layout(height=300)
            
            # Display architecture chart
            st.plotly_chart(fig_arch, width='stretch', key="arch_bar")
        else:
            st.info("Application architecture information not available")
    
    with col2:
        st.markdown("### 📈 Instance Utilization")
        instance_types = df.groupby('instance_name')['app_type'].nunique().reset_index(name='type_diversity')
        
        fig_scatter = px.scatter(
            instance_types,
            x='instance_name',
            y='type_diversity',
            size=[instance_app_counts[instance_app_counts['instance_name'] == name]['app_count'].iloc[0] for name in instance_types['instance_name']],
            title="Instance Diversity (Apps vs Types) - Click to view details",
            hover_data=['type_diversity']
        )
        fig_scatter.update_layout(height=300, xaxis_tickangle=-45)
        
        # Display scatter plot
        st.plotly_chart(fig_scatter, width='stretch', key="instance_scatter")
    
    # Additional innovative visualizations
    st.markdown("---")
    st.markdown("### 🚀 Advanced Analytics")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📊 Application Distribution by Instance")
        # Create application distribution visualization
        app_dist_data = df.groupby(['instance_name', 'app_type']).size().reset_index(name='count')
        
        if not app_dist_data.empty:
            # Create stacked bar chart showing application distribution
            fig_dist = px.bar(
                app_dist_data,
                x='instance_name',
                y='count',
                color='app_type',
                title="Application Count by Instance and Type",
                labels={'count': 'Number of Applications', 'instance_name': 'Instance'},
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig_dist.update_layout(
                height=300,
                xaxis_tickangle=-45,
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            
            st.plotly_chart(fig_dist, width='stretch', key="app_distribution")
        else:
            st.info("No application distribution data available")
    
    with col2:
        # Use the original treemap visualization
        create_treemap_visualization(df)
    
    st.markdown("</div>", unsafe_allow_html=True)

def create_visualizations(df: pd.DataFrame, metrics: Dict[str, Any]):
    """
    Create interactive visualizations using Plotly.
    
    Args:
        df: Processed DataFrame
        metrics: Summary metrics dictionary
    """
    st.subheader("📊 Data Visualizations")
    
    st.subheader("📱 Application Types Distribution")
    if metrics['app_types']:
        fig_types = px.pie(
            values=list(metrics['app_types'].values()),
            names=list(metrics['app_types'].keys()),
            title="Distribution by Application Type",
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        fig_types.update_traces(
            textposition='inside', 
            textinfo='percent+label',
            hovertemplate='<b>%{label}</b><br>Count: %{value}<br>Percentage: %{percent}<extra></extra>'
        )
        st.plotly_chart(fig_types, width='stretch')
    else:
        st.info("No application type data available")



def create_port_heatmap(df: pd.DataFrame):
    """
    Create heatmap visualization for port usage across instances.
    
    Args:
        df: Processed DataFrame
    """
    st.subheader("🔥 Port Usage Heatmap")
    
    if df.empty:
        st.info("No data available for port heatmap")
        return
    
    # Extract port information
    port_data = []
    
    for idx, row in df.iterrows():
        if pd.notna(row['ports']) and row['ports'] != 'N/A':
            try:
                # Handle different port formats
                ports_str = str(row['ports'])
                if ',' in ports_str:
                    ports = [p.strip() for p in ports_str.split(',')]
                elif ':' in ports_str:
                    ports = [p.split(':')[0] for p in ports_str.split(',')]
                else:
                    ports = [ports_str]
                
                for port in ports:
                    if port.isdigit():
                        port_data.append({
                            'instance': row['instance_name'],
                            'port': int(port),
                            'app_name': row['app_name'],
                            'app_type': row['app_type'],
                            'status': row['app_status']
                        })
            except:
                continue
    
    if port_data:
        port_df = pd.DataFrame(port_data)
        
        # Create port usage matrix
        port_matrix = port_df.groupby(['instance', 'port']).size().reset_index(name='count')
        pivot_matrix = port_matrix.pivot(index='instance', columns='port', values='count').fillna(0)
        
        if not pivot_matrix.empty:
            # Create heatmap
            fig = px.imshow(
                pivot_matrix.values,
                labels=dict(x="Port", y="Instance", color="Usage Count"),
                x=pivot_matrix.columns,
                y=pivot_matrix.index,
                color_continuous_scale='Viridis',
                title="Port Usage Across Instances"
            )
            
            fig.update_layout(
                height=max(400, len(pivot_matrix.index) * 50),
                xaxis_title="Port Number",
                yaxis_title="Instance Name"
            )
            
            st.plotly_chart(fig, width='stretch')
            
            # Application insights
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📈 Application Type Trends")
                app_type_stats = df['app_type'].value_counts()
                fig_app_trends = px.bar(
                    x=app_type_stats.values,
                    y=app_type_stats.index,
                    orientation='h',
                    title="Application Types by Count",
                    labels={'x': 'Number of Applications', 'y': 'Application Type'},
                    color=app_type_stats.values,
                    color_continuous_scale='Viridis'
                )
                fig_app_trends.update_layout(height=400)
                st.plotly_chart(fig_app_trends, width='stretch')
            
            with col2:
                st.subheader("🏢 Instance Overview")
                instance_stats = df.groupby('instance_name').agg({
                    'app_type': 'nunique',
                    'app_name': 'count'
                }).reset_index()
                instance_stats.columns = ['Instance', 'App Types', 'Total Apps']
                
                fig_instance = px.scatter(
                    instance_stats,
                    x='App Types',
                    y='Total Apps',
                    size='Total Apps',
                    hover_name='Instance',
                    title="Instance Complexity (App Types vs Total Apps)",
                    labels={'App Types': 'Number of Different App Types', 'Total Apps': 'Total Applications'}
                )
                fig_instance.update_layout(height=400)
                st.plotly_chart(fig_instance, width='stretch')
        else:
            st.info("No port usage data available for heatmap")
    else:
        st.info("No valid port data found")

def create_instance_details_page(df: pd.DataFrame):
    """
    Create comprehensive instance details page
    """
    st.markdown("<div class='page-container'>", unsafe_allow_html=True)
    st.markdown("# 🏢 Instance Details")
    st.markdown("Comprehensive analysis of instances and their applications")
    
    if df.empty:
        st.warning("No data available for analysis.")
        return
    
    # Instance selector
    instances = df['instance_name'].unique()
    
    # Check if instance was selected from overview page
    default_instance = 'All Instances'
    if 'selected_instance_for_details' in st.session_state and st.session_state.selected_instance_for_details:
        if st.session_state.selected_instance_for_details in instances:
            default_instance = st.session_state.selected_instance_for_details
        # Clear the selection after using it
        st.session_state.selected_instance_for_details = None
    
    # Find the index of default_instance in the options list
    options = ['All Instances'] + list(instances)
    default_index = options.index(default_instance) if default_instance in options else 0
    
    selected_instance = st.selectbox(
        "Select Instance for Detailed Analysis:", 
        options,
        index=default_index
    )
    
    if selected_instance != 'All Instances':
        filtered_df = df[df['instance_name'] == selected_instance]
        st.markdown(f"### 📋 Analysis for: {selected_instance}")
        
        # Instance summary
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Applications", len(filtered_df))
        with col2:
            st.metric("Application Types", filtered_df['app_type'].nunique())
        with col3:
            if 'app_name' in filtered_df.columns:
                unique_apps = filtered_df['app_name'].nunique()
                st.metric("Unique Applications", unique_apps)
            else:
                st.metric("Application Diversity", filtered_df['app_type'].nunique())
        with col4:
            st.metric("Instance ID", filtered_df['instance_id'].iloc[0] if len(filtered_df) > 0 else "N/A")
        
        # Detailed visualizations for selected instance
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Application Types in this Instance")
            app_types = filtered_df['app_type'].value_counts()
            fig_pie = px.pie(
                values=app_types.values,
                names=app_types.index,
                title=f"Applications in {selected_instance}"
            )
            st.plotly_chart(fig_pie, width='stretch')
        
        with col2:
            st.markdown("#### Application Images Distribution")
            if 'app_image' in filtered_df.columns and not filtered_df['app_image'].isna().all():
                # Show distribution of application images/versions
                image_info = filtered_df[filtered_df['app_image'].notna()]['app_image'].value_counts().head(10)
                if not image_info.empty:
                    fig_bar = px.bar(
                        x=image_info.values,
                        y=image_info.index,
                        orientation='h',
                        title="Most Used Application Images",
                        labels={'x': 'Count', 'y': 'Image'}
                    )
                    fig_bar.update_layout(height=400)
                    st.plotly_chart(fig_bar, width='stretch')
                else:
                    st.info("No application image information available")
            else:
                # Fallback to showing application name distribution
                if 'app_name' in filtered_df.columns:
                    app_name_info = filtered_df['app_name'].value_counts().head(10)
                    if not app_name_info.empty:
                        fig_bar = px.bar(
                            x=app_name_info.values,
                            y=app_name_info.index,
                            orientation='h',
                            title="Application Instances",
                            labels={'x': 'Count', 'y': 'Application Name'}
                        )
                        fig_bar.update_layout(height=400)
                        st.plotly_chart(fig_bar, width='stretch')
                    else:
                        st.info("No application name information available")
                else:
                    st.info("Application details not available")
        
        # Application list for selected instance
        st.markdown("#### Applications in this Instance")
        display_cols = ['app_name', 'app_type', 'app_status', 'ports', 'app_image'] if 'app_status' in filtered_df.columns else ['app_name', 'app_type', 'ports', 'app_image']
        available_cols = [col for col in display_cols if col in filtered_df.columns]
        st.dataframe(filtered_df[available_cols], width='stretch')
        
    else:
        # All instances overview
        st.markdown("### 📊 All Instances Overview")
        
        # Instance summary table
        instance_summary = df.groupby('instance_name').agg({
            'app_name': 'count',
            'app_type': 'nunique',
            'instance_id': 'first'
        }).rename(columns={
            'app_name': 'total_apps',
            'app_type': 'app_types',
            'instance_id': 'instance_id'
        }).reset_index()
        
        st.markdown("#### Instance Summary")
        st.dataframe(instance_summary, width='stretch')
        
        # Visualizations for all instances
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Applications per Instance")
            fig_bar = px.bar(
                instance_summary,
                x='instance_name',
                y='total_apps',
                title="Total Applications per Instance",
                color='total_apps'
            )
            fig_bar.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_bar, width='stretch')
        
        with col2:
            st.markdown("#### Type Diversity per Instance")
            fig_bar2 = px.bar(
                instance_summary,
                x='instance_name',
                y='app_types',
                title="Application Type Diversity",
                color='app_types'
            )
            fig_bar2.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_bar2, width='stretch')
    
    st.markdown("</div>", unsafe_allow_html=True)

def create_filtered_view_page(df: pd.DataFrame):
    """
    Create filtered view page based on user selection
    """
    st.markdown("<div class='page-container'>", unsafe_allow_html=True)
    st.markdown("# 🔍 Filtered View")
    
    if df.empty:
        st.warning("No data available for filtering.")
        return
    
    # Check if there's a filter from navigation
    if st.session_state.selected_filter:
        filter_type = st.session_state.selected_filter.get('type')
        filter_value = st.session_state.selected_filter.get('value')
        
        if filter_type == 'app_type':
            filtered_df = df[df['app_type'] == filter_value]
            st.markdown(f"### 🎯 Applications of type: **{filter_value}**")
            
        elif filter_type == 'instance':
            filtered_df = df[df['instance_name'] == filter_value]
            st.markdown(f"### 🏢 Applications in instance: **{filter_value}**")
            
        elif filter_type == 'app_status':
            if 'app_status' in df.columns:
                filtered_df = df[df['app_status'] == filter_value]
                st.markdown(f"### 🔧 Applications with status: **{filter_value}**")
            else:
                filtered_df = df
                st.warning(f"Status information not available. Showing all applications.")
            
        else:
            filtered_df = df
            st.markdown("### 📋 All Applications")
    else:
        filtered_df = df
        st.markdown("### 📋 All Applications")
    
    # Summary of filtered data
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Filtered Applications", len(filtered_df))
    with col2:
        st.metric("Instances Involved", filtered_df['instance_name'].nunique())
    with col3:
        st.metric("Application Types", filtered_df['app_type'].nunique())
    
    # Clear filter button
    if st.button("🔄 Clear Filter"):
        st.session_state.selected_filter = {}
        st.rerun()
    
    # Display filtered data
    if not filtered_df.empty:
        st.markdown("#### Filtered Applications Table")
        display_cols = ['instance_name', 'app_name', 'app_type', 'app_status', 'ports', 'app_image'] if 'app_status' in filtered_df.columns else ['instance_name', 'app_name', 'app_type', 'ports', 'app_image']
        available_cols = [col for col in display_cols if col in filtered_df.columns]
        st.dataframe(filtered_df[available_cols], width='stretch')
        
        # Export options
        col1, col2 = st.columns(2)
        with col1:
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                label="📥 Download as CSV",
                data=csv,
                file_name=f"filtered_applications_{filter_value if 'filter_value' in locals() else 'all'}.csv",
                mime="text/csv",
                key=get_unique_download_key("filtered_view_csv")
            )
        
        with col2:
            json_data = filtered_df.to_json(orient='records', indent=2)
            st.download_button(
                label="📥 Download as JSON",
                data=json_data,
                file_name=f"filtered_applications_{filter_value if 'filter_value' in locals() else 'all'}.json",
                mime="application/json",
                key=get_unique_download_key("filtered_view_json")
            )
    else:
        st.warning("No applications match the current filter.")
    
    st.markdown("</div>", unsafe_allow_html=True)

def create_data_table_page(df: pd.DataFrame):
    """
    Create comprehensive data table page
    """
    st.markdown("<div class='page-container'>", unsafe_allow_html=True)
    st.markdown("# 📋 Database Table")
    st.markdown("Complete application database with all details")
    
    if df.empty:
        st.warning("No data available in the database.")
        return
    
    # Search and filter options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_term = st.text_input("🔍 Search applications:", placeholder="Enter app name, type, or instance...")
    
    with col2:
        if 'app_type' in df.columns:
            app_type_filter = st.selectbox("Filter by App Type:", ['All'] + list(df['app_type'].unique()))
        else:
            app_type_filter = 'All'
    
    with col3:
        instance_filter = st.selectbox("Filter by Instance:", ['All'] + list(df['instance_name'].unique()))
    
    # Apply filters
    filtered_df = df.copy()
    
    if search_term:
        mask = (
            filtered_df['app_name'].str.contains(search_term, case=False, na=False) |
            filtered_df['app_type'].str.contains(search_term, case=False, na=False) |
            filtered_df['instance_name'].str.contains(search_term, case=False, na=False)
        )
        filtered_df = filtered_df[mask]
    
    if app_type_filter != 'All':
        filtered_df = filtered_df[filtered_df['app_type'] == app_type_filter]
    
    if instance_filter != 'All':
        filtered_df = filtered_df[filtered_df['instance_name'] == instance_filter]
    
    # Display results count
    st.markdown(f"**Showing {len(filtered_df)} of {len(df)} applications**")
    
    # Display the table
    if not filtered_df.empty:
        st.dataframe(filtered_df, width='stretch', height=600)
        
        # Export options
        st.markdown("### 📥 Export Options")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                label="📥 Download as CSV",
                data=csv,
                file_name="application_database.csv",
                mime="text/csv",
                width='stretch',
                key=get_unique_download_key("data_table_csv")
            )
        
        with col2:
            json_data = filtered_df.to_json(orient='records', indent=2)
            st.download_button(
                label="📥 Download as JSON",
                data=json_data,
                file_name="application_database.json",
                mime="application/json",
                width='stretch',
                key=get_unique_download_key("data_table_json")
            )
        
        with col3:
            # Summary statistics
            if st.button("📊 Show Summary Stats", width='stretch'):
                st.markdown("#### Summary Statistics")
                st.write(f"- Total Applications: {len(filtered_df)}")
                st.write(f"- Unique Instances: {filtered_df['instance_name'].nunique()}")
                st.write(f"- Application Types: {filtered_df['app_type'].nunique()}")
                if 'app_status' in filtered_df.columns:
                    st.write(f"- Unique Applications: {filtered_df['app_name'].nunique() if 'app_name' in filtered_df.columns else 'N/A'}")
    else:
        st.warning("No applications match the current filters.")
    
    st.markdown("</div>", unsafe_allow_html=True)

def create_instance_analysis(df: pd.DataFrame, metrics: Dict[str, Any]):
    """
    Create instance-focused analysis for management insights.
    
    Args:
        df: Processed DataFrame
        metrics: Calculated metrics dictionary
    """
    st.subheader("🏢 Instance Overview & Analysis")
    
    if df.empty:
        st.info("No data available for instance analysis")
        return
    
    # Instance summary
    instance_summary = df.groupby('instance_name').agg({
        'app_name': 'count',
        'app_type': 'nunique'
    }).rename(columns={
        'app_name': 'total_apps',
        'app_type': 'app_types'
    })
    
    # Display instance summary table
    st.subheader("📊 Instance Summary")
    st.dataframe(
        instance_summary,
        column_config={
            "total_apps": st.column_config.NumberColumn("Total Apps", format="%d"),
            "app_types": st.column_config.NumberColumn("App Types", format="%d")
        },
        width='stretch'
    )
    
    # Visualizations
    st.subheader("📈 Applications per Instance")
    fig_apps = px.bar(
        x=instance_summary.index,
        y=instance_summary['total_apps'],
        title="Total Applications by Instance",
        color=instance_summary['total_apps'],
        color_continuous_scale='Blues'
    )
    fig_apps.update_layout(showlegend=False, xaxis_title="Instance", yaxis_title="Applications")
    st.plotly_chart(fig_apps, width='stretch')
    
    # Application type distribution across instances
    st.subheader("🔄 Application Types Across Instances")
    app_type_matrix = df.groupby(['instance_name', 'app_type']).size().unstack(fill_value=0)
    
    if not app_type_matrix.empty:
        fig_matrix = px.imshow(
            app_type_matrix.values,
            labels=dict(x="Application Type", y="Instance", color="Count"),
            x=app_type_matrix.columns,
            y=app_type_matrix.index,
            color_continuous_scale='Viridis',
            title="Application Type Distribution Matrix"
        )
        fig_matrix.update_layout(height=max(400, len(app_type_matrix.index) * 50))
        st.plotly_chart(fig_matrix, width='stretch')


def create_treemap_visualization(df: pd.DataFrame):
    """
    Create treemap visualization for application hierarchy.
    
    Args:
        df: Processed DataFrame
    """
    st.subheader("🌳 Application Hierarchy Treemap")
    
    if df.empty:
        st.info("No data available for treemap")
        return
    
    # Create hierarchy data with instance -> type -> application name
    if 'app_name' in df.columns:
        # Group by instance, type, and application name
        hierarchy_data = df.groupby(['instance_name', 'app_type', 'app_name']).size().reset_index(name='count')
        
        if not hierarchy_data.empty:
            # Use app_type for color coding to distinguish different application types
            fig = px.treemap(
                hierarchy_data,
                path=['instance_name', 'app_type', 'app_name'],
                values='count',
                title="Application Hierarchy: Instance → Type → Application Name",
                color='app_type',
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            
            fig.update_layout(
                height=600,
                font_size=12
            )
            fig.update_traces(
                textinfo="label+value",
                hovertemplate='<b>%{label}</b><br>Count: %{value}<br>Path: %{currentPath}<extra></extra>'
            )
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("No hierarchy data available")
    else:
        # Fallback to instance -> type if app_name is not available
        hierarchy_data = df.groupby(['instance_name', 'app_type']).size().reset_index(name='count')
        
        if not hierarchy_data.empty:
            fig = px.treemap(
                hierarchy_data,
                path=['instance_name', 'app_type'],
                values='count',
                title="Application Hierarchy: Instance → Type",
                color='app_type',
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            
            fig.update_layout(
                height=600,
                font_size=12
            )
            fig.update_traces(
                textinfo="label+value",
                hovertemplate='<b>%{label}</b><br>Count: %{value}<br>Path: %{currentPath}<extra></extra>'
            )
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("No hierarchy data available")







# SQLite Database Functions
def init_database():
    """
    Initialize SQLite database for persistent storage
    """
    db_path = 'dashboard_data.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables if they don't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS application_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instance_id TEXT,
            instance_name TEXT,
            app_name TEXT,
            app_type TEXT,
            app_status TEXT,
            app_image TEXT,
            ports TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_tables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT UNIQUE,
            columns TEXT,
            filters TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def save_data_to_db(df: pd.DataFrame):
    """
    Save DataFrame to SQLite database
    """
    try:
        db_path = 'dashboard_data.db'
        conn = sqlite3.connect(db_path)
        
        # Clear existing data
        cursor = conn.cursor()
        cursor.execute('DELETE FROM application_data')
        
        # Insert new data
        for _, row in df.iterrows():
            cursor.execute('''
                INSERT INTO application_data 
                (instance_id, instance_name, app_name, app_type, app_status, app_image, ports)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                row.get('instance_id', ''),
                row.get('instance_name', ''),
                row.get('app_name', ''),
                row.get('app_type', ''),
                row.get('app_status', ''),
                row.get('app_image', ''),
                row.get('ports', '')
            ))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error saving to database: {str(e)}")
        return False

def load_data_from_db() -> pd.DataFrame:
    """
    Load DataFrame from SQLite database
    """
    try:
        db_path = 'dashboard_data.db'
        if not os.path.exists(db_path):
            return pd.DataFrame()
        
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query('SELECT * FROM application_data', conn)
        conn.close()
        
        # Convert ports back to list if needed
        if not df.empty and 'ports' in df.columns:
            def safe_convert_ports(x):
                if not x or x == 'nan' or x == 'None':
                    return ''
                try:
                    # Try to parse as JSON first
                    if isinstance(x, str):
                        if x.startswith('[') and x.endswith(']'):
                            ports_list = json.loads(x)
                            return ', '.join(map(str, ports_list))
                        else:
                            # Already comma-separated string, return as-is
                            return x
                    elif isinstance(x, list):
                        return ', '.join(map(str, x))
                    else:
                        return str(x)
                except:
                    return ''
            
            df['ports'] = df['ports'].apply(safe_convert_ports)
        
        return df
    except Exception as e:
        st.error(f"Error loading from database: {str(e)}")
        return pd.DataFrame()

def clear_database():
    """
    Clear all data from the database
    """
    try:
        db_path = 'dashboard_data.db'
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM application_data')
            cursor.execute('DELETE FROM user_tables')
            conn.commit()
            conn.close()
            return True
    except Exception as e:
        st.error(f"Error clearing database: {str(e)}")
        return False

def save_user_table_to_db(table_name: str, columns: list, filters: dict, custom_columns: dict = None):
    """
    Save user table configuration to database
    """
    try:
        db_path = 'dashboard_data.db'
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Update table schema to include custom_columns if it doesn't exist
        cursor.execute("PRAGMA table_info(user_tables)")
        columns_info = cursor.fetchall()
        column_names = [col[1] for col in columns_info]
        
        if 'custom_columns' not in column_names:
            cursor.execute('ALTER TABLE user_tables ADD COLUMN custom_columns TEXT DEFAULT "{}"')
        
        cursor.execute('''
            INSERT OR REPLACE INTO user_tables (table_name, columns, filters, custom_columns)
            VALUES (?, ?, ?, ?)
        ''', (table_name, json.dumps(columns), json.dumps(filters), json.dumps(custom_columns or {})))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error saving user table: {str(e)}")
        return False

def load_user_tables_from_db() -> dict:
    """
    Load user table configurations from database
    """
    try:
        db_path = 'dashboard_data.db'
        if not os.path.exists(db_path):
            return {}
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if custom_columns column exists
        cursor.execute("PRAGMA table_info(user_tables)")
        columns_info = cursor.fetchall()
        column_names = [col[1] for col in columns_info]
        
        if 'custom_columns' in column_names:
            cursor.execute('SELECT table_name, columns, filters, custom_columns, created_at FROM user_tables')
            rows = cursor.fetchall()
            
            user_tables = {}
            for row in rows:
                user_tables[row[0]] = {
                    'columns': json.loads(row[1]),
                    'filters': json.loads(row[2]),
                    'custom_columns': json.loads(row[3]) if row[3] else {},
                    'created_at': row[4]
                }
        else:
            # Fallback for older database schema
            cursor.execute('SELECT table_name, columns, filters, created_at FROM user_tables')
            rows = cursor.fetchall()
            
            user_tables = {}
            for row in rows:
                user_tables[row[0]] = {
                    'columns': json.loads(row[1]),
                    'filters': json.loads(row[2]),
                    'custom_columns': {},
                    'created_at': row[3]
                }
        
        conn.close()
        return user_tables
    except Exception as e:
        st.error(f"Error loading user tables: {str(e)}")
        return {}

def delete_user_table_from_db(table_name: str):
    """
    Delete a specific user table from database
    """
    try:
        db_path = 'dashboard_data.db'
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM user_tables WHERE table_name = ?', (table_name,))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error deleting user table: {str(e)}")
        return False

def save_custom_table_to_db(table_name: str, table_data: dict):
    """
    Save custom editable table to database
    """
    try:
        db_path = 'dashboard_data.db'
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create custom_tables table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS custom_tables (
                table_name TEXT PRIMARY KEY,
                table_data TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        ''')
        
        # Insert or update table data
        cursor.execute('''
            INSERT OR REPLACE INTO custom_tables (table_name, table_data, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        ''', (
            table_name,
            json.dumps(table_data),
            table_data.get('created_at', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error saving custom table: {str(e)}")
        return False

def load_custom_tables_from_db() -> dict:
    """
    Load custom editable tables from database
    """
    try:
        db_path = 'dashboard_data.db'
        if not os.path.exists(db_path):
            return {}
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if custom_tables table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='custom_tables'")
        if not cursor.fetchone():
            conn.close()
            return {}
        
        cursor.execute('SELECT table_name, table_data FROM custom_tables')
        rows = cursor.fetchall()
        
        custom_tables = {}
        for row in rows:
            custom_tables[row[0]] = json.loads(row[1])
        
        conn.close()
        return custom_tables
    except Exception as e:
        st.error(f"Error loading custom tables: {str(e)}")
        return {}

def delete_custom_table_from_db(table_name: str):
    """
    Delete a custom table from database
    """
    try:
        db_path = 'dashboard_data.db'
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM custom_tables WHERE table_name = ?', (table_name,))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error deleting custom table: {str(e)}")
        return False

def create_custom_editable_tables():
    """
    Create Google Sheets-like editable custom tables
    """
    st.markdown("### 📝 Custom Editable Tables")
    st.markdown("Create and edit tables like Google Sheets with full control over data")
    
    # Initialize session state for custom tables
    if 'custom_tables' not in st.session_state:
        st.session_state.custom_tables = load_custom_tables_from_db()
    if 'current_custom_table' not in st.session_state:
        st.session_state.current_custom_table = None
    if 'editing_table_data' not in st.session_state:
        st.session_state.editing_table_data = None
    
    # Sidebar for table management
    with st.sidebar:
        st.markdown("### 📋 Table Management")
        
        # Create new table section
        st.markdown("#### ➕ Create New Table")
        
        # Tab for creation method
        create_tab1, create_tab2 = st.tabs(["🆕 From Scratch", "📋 From Template"])
        
        with create_tab1:
            new_table_name = st.text_input("Table Name", placeholder="migration_table", key="new_table_name")
            
            # Define columns for new table
            st.markdown("**Define Columns:**")
            col_count = st.number_input("Number of Columns", min_value=1, max_value=10, value=4)
            
            columns = []
            for i in range(col_count):
                col_name = st.text_input(f"Column {i+1} Name", 
                                       placeholder=f"Column {i+1}", 
                                       key=f"new_col_{i}")
                if col_name:
                    columns.append(col_name)
            
            # Number of initial rows
            row_count = st.number_input("Initial Rows", min_value=1, max_value=50, value=5)
            
            if st.button("🆕 Create Empty Table", disabled=not new_table_name or len(columns) == 0):
                # Create empty table structure
                table_data = {
                    'columns': columns,
                    'data': [["" for _ in columns] for _ in range(row_count)],
                    'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                st.session_state.custom_tables[new_table_name] = table_data
                st.session_state.current_custom_table = new_table_name
                st.session_state.editing_table_data = table_data.copy()
                
                if save_custom_table_to_db(new_table_name, table_data):
                    st.success(f"Table '{new_table_name}' created successfully!")
                st.rerun()
        
        with create_tab2:
            template_table_name = st.text_input("Table Name", placeholder="app_migration_table", key="template_table_name")
            
            # Check if we have application data
            if 'processed_data' in st.session_state and not st.session_state.processed_data.empty:
                app_df = st.session_state.processed_data
                
                st.markdown("**Select Template Data:**")
                
                # Option to include all data or filter
                include_all = st.checkbox("Include all application data", value=True)
                
                if not include_all:
                    # Filter options
                    st.markdown("**Filter Data:**")
                    filter_col1, filter_col2 = st.columns(2)
                    
                    with filter_col1:
                        if 'app_type' in app_df.columns:
                            selected_types = st.multiselect(
                                "App Types:", 
                                options=app_df['app_type'].unique().tolist(),
                                default=app_df['app_type'].unique().tolist()
                            )
                        else:
                            selected_types = []
                    
                    with filter_col2:
                        if 'instance_name' in app_df.columns:
                            selected_instances = st.multiselect(
                                "Instances:", 
                                options=app_df['instance_name'].unique().tolist(),
                                default=app_df['instance_name'].unique().tolist()[:5]  # Limit default selection
                            )
                        else:
                            selected_instances = []
                    
                    # Apply filters
                    filtered_df = app_df.copy()
                    if selected_types and 'app_type' in app_df.columns:
                        filtered_df = filtered_df[filtered_df['app_type'].isin(selected_types)]
                    if selected_instances and 'instance_name' in app_df.columns:
                        filtered_df = filtered_df[filtered_df['instance_name'].isin(selected_instances)]
                else:
                    filtered_df = app_df.copy()
                
                # Select columns to include
                st.markdown("**Select Columns:**")
                available_columns = filtered_df.columns.tolist()
                # Remove technical columns that users might not want
                default_columns = [col for col in available_columns if col not in ['id', 'created_at']]
                
                selected_columns = st.multiselect(
                    "Columns to include:",
                    options=available_columns,
                    default=default_columns
                )
                
                # Add custom columns option
                st.markdown("**Add Custom Columns:**")
                custom_col_count = st.number_input("Additional Custom Columns", min_value=0, max_value=5, value=1)
                
                custom_columns = []
                for i in range(custom_col_count):
                    custom_col_name = st.text_input(
                        f"Custom Column {i+1} Name", 
                        placeholder=f"Status, Notes, Priority, etc.", 
                        key=f"custom_template_col_{i}"
                    )
                    if custom_col_name:
                        custom_columns.append(custom_col_name)
                
                # Preview the template
                if selected_columns:
                    preview_df = filtered_df[selected_columns].head(3)
                    
                    # Add custom columns to preview
                    for custom_col in custom_columns:
                        preview_df[custom_col] = ""
                    
                    st.markdown("**Preview:**")
                    st.dataframe(preview_df, use_container_width=True)
                    
                    st.info(f"Template will include {len(filtered_df)} rows and {len(selected_columns) + len(custom_columns)} columns")
                
                if st.button("📋 Create from Template", disabled=not template_table_name or not selected_columns):
                    # Create table from template
                    template_df = filtered_df[selected_columns].copy()
                    
                    # Add custom columns
                    for custom_col in custom_columns:
                        template_df[custom_col] = ""
                    
                    # Convert to table data format
                    table_data = {
                        'columns': template_df.columns.tolist(),
                        'data': template_df.values.tolist(),
                        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'template_source': 'application_data'
                    }
                    
                    st.session_state.custom_tables[template_table_name] = table_data
                    st.session_state.current_custom_table = template_table_name
                    st.session_state.editing_table_data = table_data.copy()
                    
                    if save_custom_table_to_db(template_table_name, table_data):
                        st.success(f"Table '{template_table_name}' created from template with {len(template_df)} rows!")
                    st.rerun()
            else:
                st.info("📊 No application data available. Upload data first or load from database to create templates.")
                
                if st.button("🔄 Load Data from Database"):
                    db_data = load_data_from_db()
                    if not db_data.empty:
                        st.session_state.processed_data = db_data
                        st.session_state.data_loaded = True
                        st.success(f"Loaded {len(db_data)} records from database")
                        st.rerun()
                    else:
                        st.warning("No data found in database")
        
        st.markdown("---")
        
        # Existing tables
        st.markdown("#### 📊 Existing Tables")
        if st.session_state.custom_tables:
            for table_name in st.session_state.custom_tables.keys():
                col_load, col_delete = st.columns([2, 1])
                with col_load:
                    if st.button(f"📝 {table_name}", key=f"load_custom_{table_name}"):
                        st.session_state.current_custom_table = table_name
                        st.session_state.editing_table_data = st.session_state.custom_tables[table_name].copy()
                        st.rerun()
                with col_delete:
                    if st.button("🗑️", key=f"delete_custom_{table_name}"):
                        del st.session_state.custom_tables[table_name]
                        if delete_custom_table_from_db(table_name):
                            st.success(f"Table '{table_name}' deleted!")
                        if st.session_state.current_custom_table == table_name:
                            st.session_state.current_custom_table = None
                            st.session_state.editing_table_data = None
                        st.rerun()
        else:
            st.info("No custom tables yet. Create one above!")
    
    # Main editing area
    if st.session_state.current_custom_table and st.session_state.editing_table_data:
        table_name = st.session_state.current_custom_table
        table_data = st.session_state.editing_table_data
        
        st.markdown(f"### 📝 Editing: {table_name}")
        
        # Table controls
        col_controls1, col_controls2, col_controls3 = st.columns([1, 1, 1])
        
        with col_controls1:
            if st.button("➕ Add Row"):
                table_data['data'].append(["" for _ in table_data['columns']])
                st.rerun()
        
        with col_controls2:
            if st.button("💾 Save Changes"):
                st.session_state.custom_tables[table_name] = table_data.copy()
                if save_custom_table_to_db(table_name, table_data):
                    st.success("Changes saved successfully!")
                else:
                    st.error("Failed to save changes")
        
        with col_controls3:
            if st.button("🔄 Reset Changes"):
                st.session_state.editing_table_data = st.session_state.custom_tables[table_name].copy()
                st.rerun()
        
        # Editable table interface
        st.markdown("#### 📊 Table Data")
        
        # Create DataFrame for editing
        df_data = pd.DataFrame(table_data['data'], columns=table_data['columns'])
        
        # Use st.data_editor for editable table
        edited_df = st.data_editor(
            df_data,
            use_container_width=True,
            num_rows="dynamic",
            key=f"editor_{table_name}"
        )
        
        # Update session state with edited data
        if not edited_df.equals(df_data):
            st.session_state.editing_table_data['data'] = edited_df.values.tolist()
        
        # Export options
        st.markdown("#### 📤 Export Options")
        export_col1, export_col2 = st.columns(2)
        
        with export_col1:
            csv_data = edited_df.to_csv(index=False)
            st.download_button(
                label="📄 Download as CSV",
                data=csv_data,
                file_name=f"{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                key=get_unique_download_key(f"builder_table_csv_{table_name}")
            )
        
        with export_col2:
            json_data = edited_df.to_json(orient='records', indent=2)
            st.download_button(
                label="📋 Download as JSON",
                data=json_data,
                file_name=f"{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                key=get_unique_download_key(f"builder_table_json_{table_name}")
            )
        
        # Table info
        st.markdown("#### ℹ️ Table Info")
        info_col1, info_col2, info_col3 = st.columns(3)
        with info_col1:
            st.metric("Rows", len(edited_df))
        with info_col2:
            st.metric("Columns", len(edited_df.columns))
        with info_col3:
            st.metric("Created", table_data.get('created_at', 'Unknown'))
    
    else:
        st.info("👈 Select or create a table from the sidebar to start editing")
        
        # Show example
        st.markdown("### 💡 Example: Migration Status Table")
        st.markdown("You can create tables like this:")
        
        example_data = {
            'Instance Name': ['i-k1a1to2q7byf0k4lw3hp', 'i-k1a668gjushe7pn3amp5', 'i-k1a9qchzeenayuwz0h9z'],
            'App Type': ['database', 'application', 'application'],
            'App Name': ['dab-psql-01', 'bankpro-dev01', 'billermgt-app1'],
            'Migration Status': ['on progress', 'pending', 'done']
        }
        
        example_df = pd.DataFrame(example_data)
        st.dataframe(example_df, use_container_width=True)




def main():
    """
    Main application function with multi-page navigation
    """
    # Initialize database
    init_database()
    
    # Header
    st.markdown('<div class="main-header">📊 Application Dashboard</div>', unsafe_allow_html=True)
    
    # Show error notification if any
    show_error_notification()
    
    # Navigation bar
    create_navigation_bar()
    
    # Database management section
    with st.expander("🗄️ Database Management", expanded=False):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Load from Database"):
                db_data = load_data_from_db()
                if not db_data.empty:
                    st.session_state.processed_data = db_data
                    st.session_state.data_loaded = True
                    st.success(f"Loaded {len(db_data)} records from database")
                    st.rerun()
                else:
                    st.info("No data found in database")
        
        with col2:
            if st.button("💾 Save to Database"):
                if 'processed_data' in st.session_state and not st.session_state.processed_data.empty:
                    if save_data_to_db(st.session_state.processed_data):
                        st.success("Data saved to database successfully!")
                    else:
                        st.error("Failed to save data to database")
                else:
                    st.warning("No data to save")
        
        with col3:
            if st.button("🗑️ Clear Database", type="secondary"):
                if st.session_state.get('confirm_clear', False):
                    if clear_database():
                        st.success("Database cleared successfully!")
                        # Clear session state as well
                        if 'processed_data' in st.session_state:
                            del st.session_state.processed_data
                        if 'user_tables' in st.session_state:
                            st.session_state.user_tables = {}
                        st.session_state.data_loaded = False
                        st.session_state.confirm_clear = False
                        st.rerun()
                    else:
                        st.error("Failed to clear database")
                else:
                    st.session_state.confirm_clear = True
                    st.warning("⚠️ Click again to confirm database clearing")
                    st.rerun()
    
    # Auto-load from database on startup if no data is loaded
    if not st.session_state.data_loaded and 'processed_data' not in st.session_state:
        db_data = load_data_from_db()
        if not db_data.empty:
            st.session_state.processed_data = db_data
            st.session_state.data_loaded = True
            st.info(f"Auto-loaded {len(db_data)} records from database")
    
    # File upload section (always visible)
    # Check if we have processed data to determine expander state
    has_data = 'processed_data' in st.session_state and st.session_state.processed_data is not None and not st.session_state.processed_data.empty
    with st.expander("📁 Upload Instance Data", expanded=not has_data):
        uploaded_files = st.file_uploader(
            "Choose JSON files",
            type="json",
            accept_multiple_files=True,
            help="Upload one or more JSON files containing instance and application data"
        )
        
        if uploaded_files and not st.session_state.data_loaded:
            # Process files
            start_time = datetime.now()
            
            # Clear previous errors
            st.session_state.processing_errors = []
            
            # Process data
            combined_df = process_instance_data(uploaded_files)
            
            if not combined_df.empty:
                # Show processing time
                processing_time = (datetime.now() - start_time).total_seconds()
                st.success(f"✅ Successfully processed {len(uploaded_files)} files in {processing_time:.2f} seconds")
                
                # Store in session state and mark as loaded
                st.session_state.processed_data = combined_df
                st.session_state.data_loaded = True
                
                # Auto-save to database
                if save_data_to_db(combined_df):
                    st.success("📊 Data automatically saved to database")
                else:
                    st.warning("⚠️ Failed to save data to database")
                
                st.rerun()
            else:
                st.error("❌ No valid data found in uploaded files.")
        elif uploaded_files and st.session_state.data_loaded:
            st.info("📊 Data already loaded. Using cached data for better performance.")
            if st.button("🔄 Reload Data", help="Clear cache and reload data"):
                st.session_state.data_loaded = False
                if 'processed_data' in st.session_state:
                    del st.session_state.processed_data
                st.rerun()
    
    # Check if we have data to display
    if 'processed_data' in st.session_state and not st.session_state.processed_data.empty:
        df = st.session_state.processed_data
        
        # Route to appropriate page based on current_page
        if st.session_state.current_page == 'overview':
            create_application_overview_page(df)
            
        elif st.session_state.current_page == 'instance_details':
            create_instance_details_page(df)
            
        elif st.session_state.current_page == 'filtered_view':
            create_filtered_view_page(df)
            
        elif st.session_state.current_page == 'data_table':
            create_data_table_page(df)
            

            
        else:
            # Default to overview
            st.session_state.current_page = 'overview'
            create_application_overview_page(df)
            
    else:
        # No data available
        st.markdown("## 🚀 Welcome to Application Dashboard")
        st.markdown("""
        This dashboard provides comprehensive insights into your application instances and deployments.
        
        ### 📋 Features:
        - **📊 Application Overview**: Interactive visualizations and comprehensive metrics
        - **🏢 Instance Details**: Deep dive into individual instances and their applications
        - **🔍 Filtered View**: Dynamic filtering and focused analysis
        - **📋 Database Table**: Complete searchable application database
        
        ### 🚀 Getting Started:
        1. Upload your JSON files using the upload section above
        2. Navigate through different pages using the navigation bar
        3. Interact with visualizations to filter and explore your data
        4. Export filtered data for further analysis
        
        **👆 Please upload JSON files to begin your analysis.**
        """)
        
        # Show sample data structure
        with st.expander("📖 Expected JSON Format", expanded=False):
            st.code("""
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
            """, language="json")

if __name__ == "__main__":
    main()