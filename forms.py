from django.db import models
from django.forms import ModelForm, ChoiceField
from dataview.models import DataView, Visualization, DataBackend, GoogleDataBackend, AzureDataBackend, Relation, MapVisualization, TableVisualization

class GoogleBackendForm(ModelForm):
    class Meta:
        model = GoogleDataBackend
        exclude = ['user']

class AzureBackendForm(ModelForm):
    class Meta:
        model = AzureDataBackend
        exclude = ['user']

class DataViewForm(ModelForm):
    class Meta:
        model = DataView
        exclude = ['user']

class VisualizationForm(ModelForm):
    class Meta:
        model = Visualization
        exclude = ['user']

class MapVisualizationForm(ModelForm):
    class Meta:
        model = MapVisualization
        exclude = ['user','select']

class TableVisualizationForm(ModelForm):
    class Meta:
        model = TableVisualization
        exclude = ['user','select']

class RelationForm(ModelForm):
    class Meta:
        model = Relation
        exclude = ['user']

