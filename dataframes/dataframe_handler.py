### DataFrames Handler
import os
from datetime import timedelta, datetime

from config.constants import DatabaseCollections, DEFAULT_MAX_DATE, DEFAULT_MIN_DATE
import pandas as pd


class DataFrameHandler:
    def __init__(self, db_handler, utils):
        self.raw_df = None
        self.df = None
        self.utils = utils
        self.filters_data = {
            'documents': [],
            'users': [],
            'descriptions': [],
            'uploaded-logs': [],
            'graphs': []
        }
        self.activity_over_time = []
        self.document_usage = []
        self.user_activity = []
        self.selected_log_path = DatabaseCollections.ONSHAPE_LOGS.value  # Default data source
        self.alerts_df = pd.DataFrame()
        self.db_handler = db_handler
        self.initialize_df()

    def initialize_df(self):
        try:
            data = self.db_handler.read_from_database(DatabaseCollections.ONSHAPE_LOGS.value)  # OnShape logs path acts as the default
            # data source
            if data is not None:
                self.handle_switch_log_source(data)
        except Exception as e:
            raise e

    def process_df(self):
        self._populate_uploaded_logs()
        if self.raw_df is not None:
            self._convert_time_column(dataframe=self.raw_df)
            self._extract_date_for_grouping()
            self._populate_filters()
            self._group_activity_over_time()
            self._group_document_usage()
            self._group_user_activity()
            self._generate_alerts_df()

    def update_with_new_data(self, collection_name):
        try:
            data = self.db_handler.read_from_database(collection_name)
            self._populate_uploaded_logs(data=data)
            # Only update with new data if it is set to default or if there is no data processed yet
            if data and (collection_name == DatabaseCollections.ONSHAPE_LOGS.value or self.raw_df is None):
                # Process the newly uploaded data
                self.handle_switch_log_source(data)
        except Exception as e:
            self.utils.logger.error(f"Error updating with new data: {str(e)}")

    def handle_switch_log_source(self, data, file_name=None):
        # Process the newly uploaded data
        self._dataframes_from_data(data, file_name)
        self.process_df()  # Reprocess the DataFrame

    def get_unread_alerts_count(self):
        if self.alerts_df.empty:
            return 0
        return self.alerts_df[self.alerts_df['Status'] == 'unread'].shape[0]

    def get_lightly_refined_graphs_dataframe(self):
        if self.df is not None:
            dataframe_copy = self.df.copy()
            dataframe_copy['Action'] = dataframe_copy['Description'].apply(self.utils.categorize_action)
            return dataframe_copy
        # Return an empty DataFrame with expected columns
        return pd.DataFrame(columns=['Description', 'Action', 'Time'])

    def process_graphs_layout_dataframe(self, dataframe):
        if dataframe is None:
            # Return an empty DataFrame with expected columns
            return pd.DataFrame(columns=['Time', 'Action', 'Action Type'])
        # Convert Time column to datetime
        dataframe['Time'] = pd.to_datetime(dataframe['Time'], errors='coerce')

        # Drop rows with invalid datetime values
        dataframe = dataframe.dropna(subset=['Time'])

        # Create a new column to classify actions as Advanced or Basic
        dataframe['Action Type'] = dataframe['Action'].apply(
            lambda x: 'Advanced' if x in ['Edit', 'Create', 'Delete', 'Add'] else 'Basic')

        return dataframe

    def get_max_min_dates(self, dataframe):
        if dataframe is not None and not dataframe.empty:
            # Calculate time spent on each project (Tab) regardless of the user
            dataframe['Time Diff'] = dataframe.groupby('Tab')['Time'].diff().dt.total_seconds()

            # Determine the latest date and set the default range to the last 7 days
            max_date = dataframe['Time'].max()
            min_date = dataframe['Time'].min()
            start_date = max_date - timedelta(days=7)
        else:
            # If dataframe is None or empty, use default values
            max_date = datetime.strptime(DEFAULT_MAX_DATE, '%d-%m-%Y')
            min_date = datetime.strptime(DEFAULT_MIN_DATE, '%d-%m-%Y')
            start_date = max_date - timedelta(days=7)
        return max_date, min_date, start_date

    def filter_dataframe_for_graphs(self, dataframe, selected_document, selected_log, selected_user, start_time, end_time):
        filtered_df = dataframe

        if selected_document:
            if isinstance(selected_document, list):
                filtered_df = filtered_df[filtered_df['Document'].isin(selected_document)]
            else:
                filtered_df = filtered_df[filtered_df['Document'] == selected_document]

        if selected_user:
            if isinstance(selected_user, list):
                filtered_df = filtered_df[filtered_df['User'].isin(selected_user)]
            else:
                filtered_df = filtered_df[filtered_df['User'] == selected_user]

        if start_time and end_time and filtered_df is not None:
            filtered_df['Time'] = pd.to_datetime(filtered_df['Time'], errors='coerce')
            start_date = pd.to_datetime(start_time)
            end_date = pd.to_datetime(end_time)
            filtered_df = filtered_df[(filtered_df['Time'] >= start_date) & (filtered_df['Time'] <= end_date)]

        # Group by date and count activities
        return filtered_df

    def setup_project_time_distribution_graph_dataframe(self, dataframe):
        if 'Time' not in dataframe.columns or 'Tab' not in dataframe.columns:
            return None

        dataframe['Time'] = pd.to_datetime(dataframe['Time'], errors='coerce')
        df = dataframe.dropna(subset=['Time'])

        df_sorted = df.sort_values(by=['Tab', 'Time'])
        df_sorted['Time Diff'] = df_sorted.groupby('Tab')['Time'].diff().dt.total_seconds()

        filtered_df = df_sorted.dropna(subset=['Time Diff'])
        filtered_df = filtered_df[filtered_df['Time Diff'] > 0]
        filtered_df = filtered_df[filtered_df['Time Diff'] <= 1800]

        if filtered_df.empty:
            return None

        project_time = filtered_df.groupby('Tab')['Time Diff'].sum().reset_index(name='Time Spent (seconds)')
        project_time['Time Spent (hours)'] = (project_time['Time Spent (seconds)'] / 3600).round(2)

        return project_time

    def setup_advanced_basic_actions_graph_dataframe(self, dataframe):
        if 'User' not in dataframe.columns or 'Action Type' not in dataframe.columns:
            return None
        return dataframe.groupby(['User', 'Action Type']).size().reset_index(name='Action Count')

    def setup_action_frequency_scatter_graph_dataframe(self, dataframe, start_date, end_date):
        if 'Time' not in dataframe.columns or 'User' not in dataframe.columns:
            return None

        dataframe['Time'] = pd.to_datetime(dataframe['Time'], errors='coerce')
        start_date = pd.to_datetime(start_date)
        end_date = pd.to_datetime(end_date)

        return dataframe[(dataframe['Time'] >= start_date) & (dataframe['Time'] <= end_date)]

    def setup_work_patterns_over_time_graph_dataframe(self, dataframe):
        if 'Time' not in dataframe.columns:
            return None

        dataframe['Time'] = pd.to_datetime(dataframe['Time'], errors='coerce')
        df = dataframe.dropna(subset=['Time'])

        work_patterns = df.groupby(
            [df['Time'].dt.day_name().rename('Day'), df['Time'].dt.hour.rename('Hour')]
        ).size().reset_index(name='Action Count')

        work_patterns['Time Interval'] = work_patterns['Hour'].astype(str) + ":00 - " + (
                work_patterns['Hour'] + 1).astype(str) + ":00"
        return work_patterns

    def setup_repeated_actions_by_user_graph_dataframe(self, dataframe):
        if 'User' not in dataframe.columns or 'Time' not in dataframe.columns:
            return None
        df = dataframe.sort_values(by=['User', 'Time'])
        return df.groupby(['Action', 'User', 'Description']).size().reset_index(name='Count')

    def _dataframes_from_data(self, data, file_name=None):
        data_key = None
        if file_name:
            for key, value in data.items():
                if value['fileName'] == file_name:
                    data_key = key
                    break
        if data_key is None:
            data_key = next(iter(data))  # First key
        self.df = self.raw_df = pd.DataFrame(data[data_key]['data'])

    def _convert_time_column(self, dataframe):
        # Ensure 'Time' column is properly parsed
        if 'Time' in self.raw_df.columns:
            dataframe['Time'] = pd.to_datetime(dataframe['Time'], errors='coerce')

    def extract_working_hours_data(self):
        if self.df is None:
            return None

        processed_df = self.df
        if 'Time' in self.raw_df.columns:
            self._convert_time_column(dataframe=processed_df)
            processed_df = processed_df.dropna(subset=['Time'])

            # Extract the hour of the day
            processed_df['Hour'] = processed_df['Time'].dt.hour

            # Group by User and Hour to find the distribution of work hours
            return processed_df.groupby(['User', 'Hour']).size().reset_index(name='ActivityCount')

    def _extract_date_for_grouping(self):
        # Ensure 'Date' column is correctly extracted from 'Time'
        if 'Time' in self.df.columns:
            self.df['Date'] = self.df['Time'].dt.date

    def _populate_uploaded_logs(self, data=None):
        data_to_process = data
        if data_to_process is None:
            data_to_process = self.db_handler.read_from_database(DatabaseCollections.UPLOADED_LOGS.value)
        logs = ['Default Log']
        if data_to_process:
            for key in data_to_process:
                logs.append(data_to_process[key]['fileName'])
        self.filters_data['uploaded-logs'] = logs

    def _populate_filters(self):
        if 'Document' in self.raw_df.columns:
            self.filters_data['documents'] = [doc for doc in self.raw_df['Document'].unique()]
        if 'User' in self.raw_df.columns:
            self.filters_data['users'] = [user for user in self.raw_df['User'].unique()]
        if 'Description' in self.raw_df.columns:
            self.filters_data['descriptions'] = [desc for desc in self.raw_df['Description'].unique()]

    def _group_activity_over_time(self):
        if 'Date' in self.df.columns:
            self.activity_over_time = self.df.groupby('Date').size().reset_index(name='ActivityCount')

    def _group_document_usage(self):
        if 'Document' in self.df.columns:
            self.document_usage = self.df['Document'].value_counts().reset_index(name='UsageCount')
            self.document_usage.columns = ['Document', 'UsageCount']

    def _group_user_activity(self):
        if 'User' in self.df.columns:
            self.user_activity = self.df['User'].value_counts().reset_index(name='ActivityCount')
            self.user_activity.columns = ['User', 'ActivityCount']

    def _undo_redo_activity_detection(self):
        # Filter redo and undo actions
        redo_undo_df = self.raw_df[self.raw_df['Description'].str.contains('Undo|Redo', case=False)].copy()

        # Set a time window for detecting high frequency of actions
        redo_undo_df['TimeWindow'] = redo_undo_df['Time'].dt.floor(os.environ["ALERT_TIMEWINDOW"])
        grouped = redo_undo_df.groupby(['User', 'Document', 'TimeWindow']).size().reset_index(name='Count')

        # Filter the groups that exceed the threshold
        alerts = grouped[grouped['Count'] > int(os.environ["UNDO_REDO_THRESHOLD"])].copy()

        # Prepare the alerts DataFrame
        if not alerts.empty:
            alerts['Time'] = alerts['TimeWindow'].dt.strftime('%H:%M:%S %d-%m-%Y')
            alerts['Description'] = 'Many redos/undos detected within a short time period'
            alerts['Status'] = 'unread'
            self.alerts_df = alerts[['Time', 'User', 'Description', 'Document', 'Status']]
        else:
            self.alerts_df = pd.DataFrame(columns=['Time', 'User', 'Description', 'Document', 'Status'])


    def _generate_alerts_df(self):
        self._undo_redo_activity_detection()
