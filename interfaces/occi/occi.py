from subprocess import Popen, PIPE 
import json
from datetime import datetime
import logging
import itertools



class Occi():

   command_credentials = ''
   
   def __init__(self, endpoint, auth='x509', voms=True, user_cred=None, username=None, password=None):
      self.flavors = Flavor(self)
      self.images = Image(self)
      self.servers = Compute(self)
      self.endpoint = endpoint
      self.command_credentials = " --auth %s" % auth
      
      if not username is None:
         self.command_credentials = " --username %s" % username
      if not password is None:
         self.command_credentials = " --password %s" % password
      if not user_cred is None:
         import os
         if not os.path.isfile(user_cred):
            raise Exception("proxy not found: %s" % user_cred)
         self.command_credentials += " --user-cred %s" % user_cred
      if voms:
         self.command_credentials += " --voms"
         

   def _list(self, resource):
      '''List resources. Resource should be : compute, network, storage , os_tpl , resource_tpl'''
      if not resource in ['compute', 'network', 'storage', 'os_tpl', 'resource_tpl']:
         raise Exception('Resource should be : compute, network, storage , os_tpl , resource_tpl') 
      
      command = "occi --endpoint %s --action list --resource %s" % (self.endpoint, resource)
      command += self.command_credentials 
      try:
         result_command = self.process_std(command)
      except Exception,e:
         message = e.args[0]
         message = message[message.find('Message:')+len("Message:"):len(message)-1]
         raise Exception(message)
      else:
         result = []
         for  line in result_command.split('\n'):
            if len(line) > 0:
               result.append(line[line.find('#')+1:])
         return result


   def _describe(self,resource):
      '''Describe a specific resource'''
      command = "occi --endpoint %s --action describe --resource %s" % (self.endpoint, resource)
      command += self.command_credentials
      command += ' --output-format json_extended'
      
      result = self.process_std(command)
      return json.loads(result)[0]


   def _create(self, mix_os, mix_resource, user_data, attributes={}):
      '''Create a new resource'''
      command = "occi --endpoint %s --action create --resource compute --mixin os_tpl#%s --mixin resource_tpl#%s" \
      " --context user_data=\"%s\" " % (self.endpoint, mix_os, mix_resource, user_data)
      
      for key, value in attributes.iteritems():
         command += "--attribute %s='%s' " % (key, value)
      
      command += self.command_credentials
      result = self.process_std(command)
      return result.replace('\n','')


   def _delete(self, resource):
      '''Delete a resource'''
      command = "occi --endpoint %s --action delete --resource %s" % (self.endpoint, resource)
      command += self.command_credentials
      result = None
      try:
         result = self.process_std(command)
      finally:
         return result

   
   def _link(self, resource , to_link): 
      '''Links network or storage to resource'''
      command = "occi --endpoint %s --action link --resource %s --link %s"  % (self.endpoint, resource , to_link)
      command += self.command_credentials
      result = None
      try:
         result = self.process_std(command)
      finally:
         return result


   def process_std(self,command):
      command = "/usr/local/bin/" + command
      (result,err_result)=Popen(command,bufsize=1,shell=True,stdout=PIPE,stderr=PIPE).communicate()
      
      if len(err_result) > 0:
         raise Exception(err_result + "\n" + command)
      if len(err_result) == 0  and len(result) == 0 :
         raise Exception("Unkown Error, check params: %s" % command)
   
      return result


   def _extract_param(self, text, param):
      aux = text[text.find(param+' =')+len(param)+2:]
      return aux[:aux.find('\n')].strip()



class Flavor():
   
   def __init__(self, occi):
      self.occi = occi
      
      
   def list(self):
      return self.occi._list('resource_tpl')
   
   
   def describe(self, name):
      result_describe = self.occi._describe(name)
      title = result_describe['term']
      location = result_describe['location']
      return {'title': title.strip(),
              'term': title.strip(),
              'location':location.strip()
              }
      
      
   def find(self, name=None):
      resources = []
      local_list = self.list()
      for value in local_list:
         if name in self.describe(value)['title']:
            resources.append(value)
      return resources



class Image():
   
   def __init__(self, occi):
      self.occi = occi
      
      
   def list(self):
      return self.occi._list('os_tpl')
   
   
   def describe(self, name):
      result_describe = self.occi._describe(name)
      title = result_describe['title']
      term = result_describe['term']
      location = result_describe['location']
      return {'title': title.strip(),
              'term': term.strip(),
              'location':location.strip()
              }
           
      
   def find(self, name=None):
      resources = []
      local_list = self.list()
      for value in local_list:
         description = self.describe(value)
         if name in description['title']:
            resources.append(description)
      return resources
     


class Compute():
   
   def __init__(self, occi):
      self.occi = occi
      
      
   def list(self, detailed=True, action=None):
      servers = []
      list_servers = self.occi._list('compute')
      for server in list_servers:
         try:
            if detailed:
               ob = self.describe(server)
               servers.append(ob)
               if not action is None:
                  action(ob)
            else:
               servers.append(server)
         except Exception:
            pass
      return servers
   
   
   def describe(self, name):
      def call_describe(name, error_counter=0):
         try:
            return self.occi._describe(name)
         except Exception,e:
            if "Timeout" in e.args[0]:
               error_counter = error_counter + 1
               if error_counter >= 3:
                  raise e
               return call_describe(name, error_counter)
            if "no idea" in e.args[0]:
               error_counter = error_counter + 1
               if error_counter >= 3:
                  raise e
               return call_describe(name[name.find('/compute/'):],error_counter)
            else:
               raise e
      
      try:
         description = call_describe(name)
      except Exception:
         return None
      
      vm_id = description['attributes']['occi']['core']['id']
      
      if 'hostname' in description['attributes']['occi']['compute']:
         hostname = description['attributes']['occi']['compute']['hostname']
      elif 'title' in description['attributes']['occi']['core']:
         hostname = description['attributes']['occi']['core']['title']
         
      status = description['attributes']['occi']['compute']['state']
      ip = []
      network = None
      if not status in ['inactive','error','stopped'] and len(description['links']) > 0:
         for link in itertools.ifilter(lambda x: 'networkinterface' in x['attributes']['occi'], description['links'] ):
            ip.append(link['attributes']['occi']['networkinterface']['address'])
            if 'public' in link['attributes']['occi']['core']['target']:
               network = link['attributes']['occi']['core']['id']
      elif status in ['inactive','stopped'] and len(description['links']) > 0:
         for link in description['links']:
            if 'public' in link['target']:
               network = link['id']
               
      try:      
         if "org" in description['attributes'] and "openstack" in description['attributes']['org'] and "compute" in description['attributes']['org']['openstack']:
            console = description['attributes']['org']['openstack']['compute']['console']['vnc']
            state = description['attributes']['org']['openstack']['compute']['state']
         else:
            console = None
            state = None
      except:
         console = None
         state = None
         
      #check os and flavor
      os = None
      #if len(description['mixins']) > 1:
      #  os = description['mixins'][1]
      #  os = self.occi.images.describe(os[os.index('#')+1:])
      flavor = None
      #flavor = description['mixins'][0]
      #flavor = self.occi.flavors.describe(flavor[flavor.index('#')+1:])
      return Server(self.occi, name, vm_id, hostname, status, ip, os, flavor, console, state, network)

      
   def create(self, name, image, flavor, meta={}, user_data=None, key_name=None ):
      meta = {}
      meta['occi.core.title'] = name
      import os
      if not os.path.isfile(user_data[len("file://"):]):
         raise Exception("Can't find user data file: %s" % user_data[len("file://"):])
      result = self.occi._create(image, flavor, user_data, meta)
      return self.describe(result)
   
   
   def delete(self, resource):
      try:
         return self.occi._delete(resource)
      except Exception,e:
         return self.occi._delete(resource[resource.find('/compute/'):])

   
   def link(self, resource, network):
      return self.occi._link(resource, network)



class Server():
   
   created = None
   updated = None
   

   def __init__(self, occi, resource, id, name, status, ip, os, flavor, console, state=None, network=None):
      self.occi = occi
      self.resource = resource
      self.id = id
      self.name = name
      self.status = status
      self.ip = ip
      self.os = os
      self.flavor = flavor
      if 'vcycle' in name:
         aux = name.split('-')
         self.created = aux[len(aux)-1]
      else:
         self.created = None
      self.updated = self.created
      self.console = console
      self.state = state
      self.network = network
   
      
   def delete(self):
      result = self.occi._delete(self.resource)
      if not self.network is None:
         self.occi._delete(self.network)
      return result
   
   
   def link(self, to_link):
      self.network = self.occi._link(self.resource, to_link)
      return self.network
   
   
   def __repr__(self):
      result = {'id':self.id,
                'resource':self.resource,
                'name':self.name,
                'status':self.status,
                'ip':self.ip,
                'os': self.os,
                'flavor':self.flavor,
                'created':self.created,
                'console':self.console}
      return json.dumps(result)
