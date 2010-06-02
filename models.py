from django.db import models
from django.contrib.auth.models import User
from django.utils.encoding import smart_str

BACKEND_CHOICES = (
    ('1','Azure'),
)

VIZ_CHOICES = (
    (1,"Time Series"),
    (2,"Table"),
    (3,"Scatter Plot"),
    (4,"Map"),
)

BACKEND_CHOICES = (
    (1,"Google Spreadsheets"),
    (2,"MS Windows Azure Table Services"),
)

class  DataBackend(models.Model):
    user = models.ForeignKey(User)
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=255)

    def __str__(self):
        return smart_str("%s" % (self.name))

class GoogleDataBackend(DataBackend):
    access_token = models.CharField(max_length=255)
    token_secret = models.CharField(max_length=255)

    def __str__(self):
        return smart_str("%s (Google)" % (self.name))

class AzureDataBackend(DataBackend):
    azure_username = models.CharField(max_length=255)
    secret_key = models.CharField(max_length=255)
    
    def __str__(self):
        return smart_str("%s (Azure)" % (self.name))

class DataView(models.Model):
    user = models.ForeignKey(User,editable=True)
    backend = models.ForeignKey(DataBackend)
    tablename = models.CharField(max_length=255)
    columns = models.TextField()
    query = models.TextField()

    def __str__(self):
        return smart_str("%d. '%s' table with %s fields." % (self.pk,self.tablename,self.columns))

class Visualization(models.Model):
    user = models.ForeignKey(User,editable=False)
    name = models.CharField("Name",max_length=255)
    dataview = models.ForeignKey(DataView)
    viz_type = models.IntegerField("Visualization Type",choices=VIZ_CHOICES)
    
    def save(self, *args, **kwargs):
        super(Visualization, self).save(*args, **kwargs) 


    def __str__(self):
        return smart_str("%s" % self.name)

