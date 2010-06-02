from django.shortcuts import render_to_response
from django.core.context_processors import csrf
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.template import RequestContext
from django import forms
from django.db import models
from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ObjectDoesNotExist
from django.views.decorators.csrf import csrf_exempt
from dataview.models import DataView, Visualization, DataBackend, GoogleDataBackend, AzureDataBackend
from dataview.forms import DataViewForm, VisualizationForm, GoogleBackendForm, AzureBackendForm
import winazurestorage as azure
import xml.dom.minidom
import xml.etree.ElementTree as ET

import opus.lib
log = opus.lib.log.getLogger()
import dataview_settings as dvsettings 
from GChartWrapper import GChart, Scatter, LineXY

import datetime
import gviz_api
import urlparse
import oauth2 as oauth
import cgi

try:
  from xml.etree import ElementTree
except ImportError:
  from elementtree import ElementTree
import gdata.spreadsheet.service
import gdata.service
import atom.service
import gdata.spreadsheet
import atom
import getopt
import sys
import string



# TODO: Check if store was created succesfully

def _get_store(): 
    store = azure.TableStorage(dvsettings.CLOUD_TABLE_HOST, dvsettings.DEVSTORE_ACCOUNT, dvsettings.DEVSTORE_SECRET_KEY)
    return store

def check_request_type(request, table_name):
    if request.method == 'GET':
        return get_all_in_table(request, table_name)    
    if request.method == 'POST':
        return insert(request, table_name)
    if request.method == 'PUT':
        return create_table(request,table_name)
    if request.method == 'DELETE':
        return delete_table(request, table_name)

@login_required
def data_backend(request):
    return render_to_response('dataview/databackend.html')

@login_required
def google_backend(request,be_pk=None): 
    if request.method == 'GET': 
        if be_pk == None:
            gdb = GoogleDataBackend(user=request.user)
            redirect_url = "https://" + request.META['HTTP_HOST'] + reverse('google-backend-form')
        else:
            gdb = GoogleDataBackend.objects.get(pk=be_pk)
            redirect_url = "https://" + request.META['HTTP_HOST'] + reverse('edit-google-backend-form',args=[be_pk])
        if 'oauth_token' in request.GET:
            access_token_url = 'https://www.google.com/accounts/OAuthGetAccessToken'
            # Step 1. Use the request token in the session to build a new client.
            token = oauth.Token(request.session['request_token']['oauth_token'],
            request.session['request_token']['oauth_token_secret'])
            consumer = oauth.Consumer(dvsettings.GOOGLE_CONSUMER_KEY, dvsettings.GOOGLE_CONSUMER_SECRET)
            client = oauth.Client(consumer, token)
            # Step 2. Request the authorized access token from Twitter.
            resp, content = client.request(access_token_url, "GET")
            if resp['status'] != '200':
                log.debug(content)
                raise Exception("Invalid response from Twitter.")
            access_token = dict(cgi.parse_qsl(content))
            log.debug(access_token)            
            c = {}
            c.update(csrf(request))
            gdb.access_token = access_token['oauth_token']
            gdb.token_secret = access_token['oauth_token_secret']


            if be_pk == None:
                c.update({'action':reverse('google-backend-form')})
            else:
                c.update({'action':reverse('edit-google-backend-form', args=[be_pk])})
            c.update({'form':GoogleBackendForm(instance=gdb)})
            return render_to_response("dataview/googlebackend.html",c)
        else:
            log.debug(request.GET)
            request_token_url = 'https://www.google.com/accounts/OAuthGetRequestToken?scope=https://spreadsheets.google.com/feeds/'
            authorize_url = 'https://www.google.com/accounts/OAuthAuthorizeToken'
            consumer = oauth.Consumer(dvsettings.GOOGLE_CONSUMER_KEY, dvsettings.GOOGLE_CONSUMER_SECRET)
            client = oauth.Client(consumer)

# Step 1: Get a request token. This is a temporary token that is used for 
# having the user authorize an access token and to sign the request to obtain 
# said access token.

            resp, content = client.request(request_token_url, "GET")
            if resp['status'] != '200':
                raise Exception("Invalid response %s." % resp['status'])

            request.session['request_token'] = dict(cgi.parse_qsl(content))
            log.debug(redirect_url)
            forwarding_url = "%s?oauth_token=%s&oauth_callback=%s" % (authorize_url, request.session['request_token']['oauth_token'],redirect_url)
            return HttpResponseRedirect(forwarding_url) # Redirect after POST
    if request.method == 'POST':
        if be_pk == None:
            be = GoogleDataBackend(user=request.user)
        else:
            #this is an edit, so fill in pk and user 
            be = GoogleDataBackend(user=request.user,pk=be_pk)
        log.debug(request.POST)
        form = GoogleBackendForm(request.POST,instance=be) # A form bound to the POST data
        if form.is_valid(): # All validation rules pass
            log.debug("got here")
            form.save()
            return HttpResponseRedirect('/dataview/backend/all/') # Redirect after POST

@login_required
def azure_backend(request,be_pk=None):
    c = {}
    c.update(csrf(request))
    if request.method == 'POST':
        if be_pk == None:
            be = AzureDataBackend(user=request.user)
        else:
            #this is an edit, so fill in pk and user 
            be = AzureDataBackend(user=request.user,pk=be_pk)
        form = AzureBackendForm(request.POST,instance=be) # A form bound to the POST data
        if form.is_valid(): # All validation rules pass
            form.save()
            return HttpResponseRedirect('/dataview/backend/all/') # Redirect after POST
    if request.method == 'GET':
        if be_pk == None:
            c.update({'action':reverse('azure-backend-form')})
            adb = AzureDataBackend(user=request.user)
        else:
            c.update({'action':reverse('edit-azure-backend-form', args=[be_pk])})
            adb = AzureDataBackend.objects.get(pk=be_pk)
        c.update({'form':AzureBackendForm(instance=adb)})
        return render_to_response("dataview/azurebackend.html",c)

@login_required
def list_backends(request):
    googlebackends = GoogleDataBackend.objects.filter(user=request.user)
    azurebackends = AzureDataBackend.objects.filter(user=request.user)
    return render_to_response('dataview/backendlist.html',{'google':googlebackends, 'azure':azurebackends})

def _PrintFeed(feed):
    for i, entry in enumerate(feed.entry):
      if isinstance(feed, gdata.spreadsheet.SpreadsheetsCellsFeed):
        log.debug('%s %s\n' % (entry.title.text, entry.content.text))
      elif isinstance(feed, gdata.spreadsheet.SpreadsheetsListFeed):
        log.debug('%s %s %s' % (i, entry.title.text, entry.content.text))
        # Print this row's value for each column (the custom dictionary is
        # built using the gsx: elements in the entry.)
        log.debug('Contents:')
        for key in entry.custom:
          log.debug('  %s: %s' % (key, entry.custom[key].text))
        print '\n',
      else:
        log.debug('%s %s\n' % (i, entry.title.text))

def viz_data_source(request,dv_pk):
    new_schema = {}
    new_entities = []
    dv = DataView.objects.get(pk=dv_pk)
    try:
        gdb = GoogleDataBackend.objects.get(pk=dv.backend)
        token = oauth.Token(gdb.access_token.encode('utf-8'),gdb.token_secret.encode('utf-8'))
        log.debug(token)
        consumer = oauth.Consumer(dvsettings.GOOGLE_CONSUMER_KEY, dvsettings.GOOGLE_CONSUMER_SECRET)
        client = oauth.Client(consumer, token)
        #resp, content = client.request("https://spreadsheets.google.com/feeds/spreadsheets/private/full")
        #resp, content = client.request("https://spreadsheets.google.com/feeds/worksheets/tRARFk7qXeamBKNL62g7iPQ/private/full")
        #resp, content = client.request("https://spreadsheets.google.com/feeds/spreadsheets/private/full/tRARFk7qXeamBKNL62g7iPQ")
        resp, content = client.request("https://spreadsheets.google.com/tq?key=0AoX3D_W26UJsdFJBUkZrN3FYZWFtQktOTDYyZzdpUFE&range=A1:B5")
        if resp['status'] != '200':
            log.debug(content)
            raise Exception("Invalid response from Spreadsheets.")
        log.debug("this is google")
        log.debug(content)
        return HttpResponse(content)
        #feed = gdata.GDataFeedFromString(content)
        #id_parts = feed.entry[string.atoi(1)].id.text.split('/')
        #curr_wksht_id = id_parts[len(id_parts) - 1]
        #_PrintFeed(feed)
        for entry in feed:
            log.debug(entry)



    except GoogleDataBackend.DoesNotExist:
        log.debug("this is azure")
        store = _get_store()
        entities,schema = store.query(dv.tablename, dv.query)
        log.debug(schema)
        columns = dv.columns.encode('utf-8').split(',')
        for key in columns:
            new_schema[key] = schema.pop(key)
        
        for entity in entities:
            new_entity = {}
            for key in columns:
                new_entity[key] = entity.pop(key)
            new_entities.append(new_entity)
        log.debug(columns[0])
        data_table = gviz_api.DataTable(new_schema)
        data_table.LoadData(new_entities)
        return HttpResponse(data_table.ToJSonResponse(columns_order=columns,order_by=columns[0]))

def google_test(request):
    return render_to_response("dataview/googlefeed.html")

@login_required
def dataview_home(request):
    has_viz = len(Visualization.objects.filter(user = request.user))
    has_views = len(DataView.objects.filter(user = request.user))
    return render_to_response("dataview/home.html",{'has_views':has_views, 'has_viz':has_viz})

#@login_required
def dataview_visualizations(request):
    pass

@login_required
def list_dataviews(request):
    dataviews = DataView.objects.filter(user=request.user)
    return render_to_response('dataview/dataviewlist.html', {
        'dataviews':dataviews,
    })

@login_required
def dataview(request, dv_pk=None):
    c = {}
    c.update(csrf(request))
    if request.method == 'POST': # If the form has been submitted...
        if dv_pk == None:
            dv = DataView(user=request.user)
        else:
            #this is an edit, so fill in pk and user 
            dv = DataView(user=request.user,pk=dv_pk)
        form = DataViewForm(request.POST,instance=dv) # A form bound to the POST data
        if form.is_valid(): # All validation rules pass
            form.save()
            return HttpResponseRedirect('/dataview/dataview/all/') # Redirect after POST
    else:
        if dv_pk == None:
            form = DataViewForm() # An unbound form
            c.update({'action':reverse('dataview-form')})
        else:
            dv = DataView.objects.get(pk=dv_pk)
            form = DataViewForm(instance=dv)
            c.update({'action':reverse('edit-dataview-form',args=[dv_pk])})
    c.update({'form':form})
    return render_to_response('dataview/create_dataview.html', c)

@login_required
def list_visualizations(request):
    visualizations = Visualization.objects.filter(user=request.user)
    return render_to_response('dataview/visualizationlist.html', {
        'visualizations':visualizations,
    })

@login_required
def visualization(request,viz_pk=None):
    c = {}
    c.update(csrf(request))
    if request.method == 'POST':
        if viz_pk == None:
            dv = Visualization(user=request.user)
        else:
            #this is an edit, so fill in pk and user 
            dv = Visualization(user=request.user,pk=viz_pk)
        form = VisualizationForm(request.POST,instance=dv)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect('/dataview/visualization/all')
    else:
        if viz_pk == None:
            form = VisualizationForm()
        else:
            viz = Visualization.objects.get(pk=viz_pk)
            form = VisualizationForm(instance=viz)
    c.update({'form':form,'action':request.path})
    return render_to_response('dataview/visualization.html', c)

def chart(request,viz_pk):
    viz = Visualization.objects.get(pk=viz_pk)
    #If backend is Azure
    if viz.viz_type == 1:
        return render_to_response('dataview/timeseries.html',{'dataview':viz.dataview.pk,'width':700,'height':240})
    if viz.viz_type == 2:
        return render_to_response('dataview/table.html',{'dataview':viz.dataview.pk})
    if viz.viz_type == 3:
        return render_to_response('dataview/scatter.html',{'dataview':viz.dataview.pk,'width':600,'height':500})
    if viz.viz_type == 4:
        return render_to_response('dataview/map.html',{'dataview':viz.dataview.pk})


@csrf_exempt
def create_table(request, table_name):
    '''TODO:
    check header for user and satisfy the request with proper account
    check if service requested is Azure or Gdata
    check if request was a post
    '''
    store = _get_store()
    response = store.create_table(table_name)

    return HttpResponse(response,mimetype="xml")

def delete_table(request, table_name):
    store = _get_store()
    response = store.delete_table(table_name)
    return response 

def list_tables(request):
    store = _get_store()
    response = store.list_tables()
    return HttpResponse(response, mimetype="xml")

def get_entry(request, table_name, row_key, partition_key):
    store = _get_store()
    log.debug("table_name: %s" % table_name)
    response = store.get_entity(table_name, partition_key, row_key)
    return HttpResponse(response, mimetype="xml")

def get_all_in_table(request, table_name):
    store = _get_store()
    response = store.get_all(table_name)
    return HttpResponse(response, mimetype="xml")

@csrf_exempt
def insert(request,table_name):
    store = _get_store()
    log.debug(request.raw_post_data)

    response = store.insert_entry(table_name,request.raw_post_data)
    return HttpResponse(response.read(), mimetype="xml")
