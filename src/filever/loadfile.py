
import sys
import hashlib
import shutil
import socket
import os
import pwd
import grp
import datetime
import configparser
import re
import json
from os.path import expanduser
from os.path import basename
from pick import pick
from operator import itemgetter

# self.vault    (default: "~/.vault/")
# self.vtable   ("versions.table" as dictionary)
# self.newname  (name when "-n" specified)
# self.dironly  (listing or restoring with no filename)
# self.dirname  (name of directory when dironly True)
# self.meta     (dictionary):
#   hashval           key
#   filename:comment  0 (dictionary)
#   fqdn              1
#   uid               2 
#   gid               3
#   perms             4
#   versionval        5
#   filesize          6

blankfile="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

class loadfile(object):
  def __init__(self,name,newname="",comment=""):
    home = expanduser("~")
    config = configparser.ConfigParser()
    configfiledir = ( home + '/.config/filever')

    if not os.path.isfile(configfiledir+"/filever.conf"):
      if not os.path.exists(configfiledir):
        os.makedirs(configfiledir)
      configfileobject = open(configfiledir+"/filever.conf", 'a+')
      configfileobject.write("[Main]\n")
      configfileobject.write('vault = ~/.vault\n')
      configfileobject.write("\n")
      configfileobject.close()

    config.read( configfiledir + '/filever.conf')
    tmpvault = config.get('Main', 'vault')
    self.vault = tmpvault.replace("~", home)
    if not os.path.isfile(self.vault+"/versions.table"):
      if not os.path.exists(self.vault):
        os.makedirs(self.vault)
      if not os.path.exists(self.vault+"/versions"):
        os.makedirs(self.vault+"/versions")
      open(self.vault+"/versions.table", 'a+').close()
    vtable = vaultfio("read",self.vault)
    self.vtable = vtable
    versionlabel=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    self.newname=newname
    self.dironly=False
    self.meta=[]
    if os.path.isdir(name):
      self.dironly=True
      name=os.path.abspath(name)
      self.dirname=name
    if os.path.isfile(name):
      name=os.path.abspath(name)
      hashval = gen_hash(name)
      uid = os.stat(name).st_uid
      uid = pwd.getpwuid(uid).pw_name
      gid = os.stat(name).st_gid
      gid = grp.getgrgid(gid)[0]
      perms = os.stat(name).st_mode
      filesize = os.path.getsize(name)
    else: # name does not exist: either restoring a deleted file or a grep string
      hashval = "0"
      uid = "unknown"
      gid = "unknown"
      perms = "unknown"
      filesize = "0"
    if not self.dironly:
      self.meta.append(hashval)
      self.meta.append({name:comment})
      self.meta.append(socket.getfqdn())
      self.meta.append(uid)
      self.meta.append(gid)
      self.meta.append(str(perms))
      self.meta.append(versionlabel)
      self.meta.append(filesize)

  def backup(self):
    newhash=False
    updatedhash=False
    hashexists,fileexists = check_if_exists(self.meta,self.vtable)
    if not hashexists: # file has never been backed up, not in vault
      self.vtable[self.meta[0]]=self.meta[1:]
      copyfile(list(self.meta[1].keys())[0], self.vault+"/versions/"+self.meta[0],self.vault) # backup physical file
      newhash=True
    if hashexists and not fileexists: # hash exists, just update new filename
      localfilename=list(self.meta[1].keys())[0]
      localcomment=list(self.meta[1].values())[0]
      self.vtable[self.meta[0]][0][localfilename]=localcomment   # add filename/comment to dictionary
      updatedhash=True
    if newhash or updatedhash: #write dictionary and clone vault
      vaultfio("write",self.vault,self.vtable)
    return [newhash,updatedhash]

  def list_backups_by_hash(self):
    if check_if_exists(self.meta,self.vtable)[0]:
      fndict_from_vault=self.vtable[self.meta[0]][0]
      localfilename=list(self.meta[1].keys())[0]
      if ( (len(fndict_from_vault) != 1 and localfilename not in fndict_from_vault.keys()) or len(fndict_from_vault) > 1):
        print ("Known filenames for current version:\n")
        for filename, comment in fndict_from_vault.items():
          if filename != localfilename:
            if comment:
              print (" > %s (%s)" % (filename,comment))
            else:
              print (" > %s" % (filename))
        print ("")

  def list_backups_by_name(self):
    versionlist=[]
    backedup=False
    localfilename=list(self.meta[1].keys())[0]
    localhash=self.meta[0]
    for thehash, thevallist in self.vtable.items():
      for filename, comment in thevallist[0].items():
        if filename == localfilename:
          if thehash == localhash:
            versionlist.append([thehash,filename," X ",thevallist[5],comment,thevallist[6]])
            backedup=True
          else:
            versionlist.append([thehash,filename,"   ",thevallist[5],comment,thevallist[6]])
    if not backedup and self.meta[0] != "0":
      print ("\nWARNING: Current version not backed up!")
    elif backedup:
      print ("\nFile is backed up!")
    if len(versionlist) > 0:
      versionlist=sorted(versionlist, key=itemgetter(3))
      print ("\nVersions available:\n")
      for arecord in versionlist:
        if arecord[4] != "":
          print (" - %s %11d %s%s - %s" % (arecord[3],arecord[5],basename(arecord[1]),arecord[2],arecord[4]))
        else:
          print (" - %s %11d %s%s" % (arecord[3],arecord[5],basename(arecord[1]),arecord[2]))
    print ("")

  def list_backups_for_dir(self):
    versionlist=[]
    backedup=False
    for vaulthash, vaultlist in self.vtable.items():
      for vaultfile, comment in vaultlist[0].items():
        if os.path.dirname(vaultfile) == self.dirname:
          versionlist.append([vaulthash,vaultfile,"   ",vaultlist[5],comment,vaultlist[6]])
    if len(versionlist) > 0:
      versionlist=sorted(versionlist, key=itemgetter(3))
      print ("\nFiles that have been backed up in %s:\n" % (self.dirname))
      for arecord in versionlist:
        if arecord[4]:
          print (" - %s %11d %s%s - %s" % (arecord[3],arecord[5],basename(arecord[1]),arecord[2],arecord[4]))
        else:
          print (" - %s %11d %s%s" % (arecord[3],arecord[5],basename(arecord[1]),arecord[2]))
    print ("")

  def restore_backups_for_dir(self,delfile=False):
    versionlist=[]
    backedup=False
    for vaulthash, vaultval in self.vtable.items():
      for vaultfilename, comment in vaultval[0].items():
        if os.path.dirname(vaultfilename) == self.dirname:
          versionlist.append([vaulthash,vaultfilename,"   ",vaultval[5],comment,vaultval[4],vaultval[6]]) 
    if len(versionlist) > 0:
      versionlist=sorted(versionlist, key=itemgetter(3))
      menulist=[]
      for arecord in versionlist:
        menulist.append(" %s %11d %s%s %s" % (arecord[3],arecord[6],basename(arecord[1]),arecord[2],arecord[4]))
      menulist.append(" abort")
      if delfile:
        option, index = pick(menulist, "Backups available for deletion from vault:")
      else:
        option, index = pick(menulist, "Backups available for specified directory:")
      if option == " abort":
        print ("\ncancelled\n")
        sys.exit()
      hash_to_restore = ("%s" % (versionlist[index][0]))
      file_to_restore = ("%s" % (versionlist[index][1]))
      file_permissions = ("%s" % (versionlist[index][5]))
      if self.newname:
        file_to_restore=self.newname
      copyfile(self.vault+"/versions/"+hash_to_restore,file_to_restore,self.vault,delfile,hash_to_restore)
      if delfile:
        remove_from_table(self.vault, hash_to_restore, file_to_restore)
        print ("\nFile %s removed from vault." % (file_to_restore))
      else:
        origperm=int(file_permissions)
        os.chmod(file_to_restore, origperm)  # set permissions just in case copy2 didn't do it.
        print ("\nFile %s restored." % (file_to_restore))
    print ("")

  def restore_backup_by_name(self,delfile=False,latest=False):
    versionlist=[]
    backedup=False
    searchstring=re.compile(list(self.meta[1].keys())[0],re.I)
    for vaulthash, vaultval in self.vtable.items():
      for vaultfilename, comment in vaultval[0].items():
        hit = searchstring.search(vaultfilename)
        if hit:                                   
          if vaulthash == self.meta[0]:
            versionlist.append([vaulthash,vaultfilename," X ",vaultval[5],comment,vaultval[4],vaultval[6]])
            backedup=True
          else:
            versionlist.append([vaulthash,vaultfilename,"   ",vaultval[5],comment,vaultval[4],vaultval[6]])
    if len(versionlist) > 0:
      versionlist=sorted(versionlist, key=itemgetter(3))
      menulist=[]
      for arecord in versionlist:
        menulist.append(" %s %11d %s%s %s" % (arecord[3],arecord[6],basename(arecord[1]),arecord[2],arecord[4]))
      menulist.append(" abort")
      if delfile:
        option, index = pick(menulist, "Versions available for removal from vault:")
      else:
        if not latest and len(versionlist) > 1:
          option, index = pick(menulist, "Versions available:")
        else:
          option = ""
          index=0
          if len(versionlist) > 1:
            index = -1 
      if option == " abort":
        print ("\ncancelled\n")
        sys.exit()
      hash_to_restore = ("%s" % (versionlist[index][0]))
      file_to_restore = ("%s" % (versionlist[index][1]))
      file_permissions = ("%s" % (versionlist[index][5]))
      if self.newname:
        file_to_restore=self.newname
      copyfile(self.vault+"/versions/"+hash_to_restore,file_to_restore,self.vault,delfile,hash_to_restore)
      if delfile:
        remove_from_table(self.vault, hash_to_restore, file_to_restore)
        print ("\nFile %s removed from vault." % (file_to_restore))
      else:
        origperm=int(file_permissions)
        os.chmod(file_to_restore, origperm)  # set permissions just in case copy2 didn't do it.
        print ("\nFile %s restored." % (file_to_restore))
    print ("")

  def show_vault_contents(self):
    versionlist=[]
    for vaulthash, vaultval in self.vtable.items():
      for thefilename, comment in vaultval[0].items(): 
        versionlist.append([vaulthash,thefilename,"   ",vaultval[5],comment,vaultval[6]])
    if len(versionlist) > 0:
      versionlist=sorted(versionlist, key=itemgetter(3))
      print ("\nVault Contents:\n")
      for arecord in versionlist:
        if arecord[4] != "":
          print (" - %s %11d %s%s - %s" % (arecord[3],arecord[5],arecord[1],arecord[2],arecord[4]))
        else:
          print (" - %s %11d %s%s" % (arecord[3],arecord[5],arecord[1],arecord[2]))
    print ("")

def check_if_exists(localmetadata,vtable):
  hashexists=False
  fileexists=False
  localhash=localmetadata[0]
  localfilename=list(localmetadata[1].keys())[0]
  if vtable.get(localhash):
    hashexists=True
    fndict=vtable[localhash][0]
    if localfilename in fndict.keys():
      fileexists=True
  return [hashexists,fileexists]

def vaultfio(iotype,vault,vtable={}):
  if iotype == "write":
    with open(vault+"/versions.table","w") as outputfile: 
      json.dump(vtable, outputfile)
    copyfile(vault+"/versions.table", vault+"/versions/",vault) # make a backup of the vault
  elif iotype == "read":
    with open(vault+"/versions.table","r") as inputfile: 
      try:
        vtable=json.load(inputfile)
      except ValueError:
        vtable={}
  return vtable

def copyfile(sourcefile,destfile,vault,delfile=False,filehashval=blankfile):
  vtable = vaultfio("read",vault)
  if delfile:
    if vtable.get(filehashval):
      if len(vtable[filehashval][0]) == 1:
        os.remove(sourcefile)
  else:
    if os.path.isfile(destfile):
      okhash = False
      okname = False
      BUF_SIZE = 65536  # read in 64k blocks
      sha256 = hashlib.sha256()
      filehashval = gen_hash(destfile)
      if vtable.get(filehashval):
        okhash = True
        for vaultfilename, comment in vtable[filehashval][0].items():
          if vaultfilename == destfile:
            okname = True
      if not okhash or not okname:
        print ("\nWARNING: Current version not backed up!")
        tocontinue = input("\nContinue anyway? (y|N): ").lower()
        if tocontinue != "y":
          print ("\nAborting...\n")
          sys.exit()
    shutil.copy2(sourcefile, destfile)

def remove_from_table(vault, hashvalue, filename):
  vtable = vaultfio("read",vault)
  filelist = vtable[hashvalue][0]
  for vaultfilename in list(filelist):
    if vaultfilename == filename:
      del filelist[vaultfilename]
  if len(filelist) == 0:
    del vtable[hashvalue]
  vaultfio("write",vault,vtable)

def gen_hash(somefile):
  filehashval = blankfile
  BUF_SIZE = 65536  # read in 64k blocks
  sha256 = hashlib.sha256()
  with open(somefile, 'rb') as f:
    while True:
      data = f.read(BUF_SIZE)
      if not data:
        break
      sha256.update(data)
      filehashval = ("{0}".format(sha256.hexdigest()))
  return filehashval
