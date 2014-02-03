# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
Hook that gets called to store publish data for a path being submitted to Perforce
"""

import sgtk
from sgtk import TankError
from tank_vendor import yaml

import os, sys
import tempfile

PENDING_PUBLISHED_FILE_ENTITY = "CustomEntity27"
         
class StorePublishData(sgtk.Hook):
    
    def execute(self, local_path, user, workspace, data, **kwargs):
        """
        Store the specified publish data so that it can be retrieved lated by
        the corresponding load_publish_data hook
        
        :local_path:    String
                        Local path to the file being published
                        
        :user:          Dictionary
                        Shotgun HumanUser entity dictionary
                        
        :workspace:     String
                        The Perforce workspace/client that path is being published in                     
                     
        :data:          Dictionary
                        Dictionary of data to store for the published file.  This data will match the
                        parameters expected by the 'sgtk.util.register_publish()' function.
        """
        p4_fw = self.parent
        p4_util = p4_fw.import_module("util")

        # we'll need a Perforce connection:
        p4 = p4_fw.connect()
        
        # all publish paths stored in Shotgun are depot paths so first we need
        # to convert all paths in the data to depot paths:
        dependency_paths = data.get("dependency_paths", [])
        p4_file_details = p4_util.get_client_file_details(p4, [local_path] + dependency_paths)
        
        depot_path = p4_file_details[local_path].get("depotFile")
        if not depot_path:
            raise TankError("Failed to determine depot location for local path '%s'!" % local_path)

        depot_dependency_paths = []
        for dp in dependency_paths:
            ddp = p4_file_details[dp].get("depotFile")
            if ddp:
                # only care about dependency paths that have valid depot paths
                # (TODO) - maybe this should error?
                depot_dependency_paths.append(ddp)

        head_revision = int(p4_file_details[local_path].get("headRev", 0))
                 
        # Create a new PendingPublishedFile entity to store this data in the following fields:
        # - sg_workspace (text)
        # - sg_published_file_type (text)
        # - sg_entity (entity, Asset/Level)
        # - sg_task (entity, Task)
        # - sg_metadata (File/link)
        # - sg_head_revision (int)
        
        # build data for new entity:
        create_data = {"code":depot_path,
                       "project":p4_fw.context.project,
                       "created_by":user,
                       "sg_workspace":workspace,
                       "sg_head_revision":head_revision
                       }
        
        if "comment" in data:
            create_data["description"] = data.get("comment", "")
        if "published_file_type" in data:
            create_data["sg_published_file_type"] = data.get("published_file_type", "")                        
        
        task = data.get("task")
        ctx = data.get("context")
        if ctx:
            if ctx.entity:
                create_data["sg_entity"] = ctx.entity
            if not task:
                task = ctx.task
        if task:
            create_data["sg_task"] = task
                       
        # create the entity:
        sg_res = p4_fw.shotgun.create(PENDING_PUBLISHED_FILE_ENTITY, create_data)
        
        # upload the thumbnail:
        thumbnail_path = data.get("thumbnail_path")
        if thumbnail_path and os.path.exists(thumbnail_path):
            # we can store the thumbnail directly on the entity
            p4_fw.shotgun.upload_thumbnail(sg_res["type"], sg_res["id"], thumbnail_path)
            
        # store dependencies in a yaml file and upload:
        #
        metadata = {"dependency_paths":depot_dependency_paths}
        md_display_name = "%s.yml" % (local_path.split("/")[-1] or "metadata")
            
        yml_path = None
        try:
            # get temporary file to use:
            # to be cross-platform and python 2.5 compliant, we can't use
            # tempfile.NamedTemporaryFile with delete=False.  Instead, we
            # use tempfile.mkstemp which does practically the same thing!
            yml_file, yml_path = tempfile.mkstemp(suffix=".yml", prefix="publish_metadata_", text=True)
            if yml_file:
                os.close(yml_file)
                
            # serialise data:
            yaml.dump(metadata, open(yml_path, "w"))
                
            # upload data to shotgun:
            p4_fw.shotgun.upload(entity_type = sg_res["type"], 
                                 entity_id = sg_res["id"], 
                                 path = yml_path, 
                                 field_name = "sg_metadata", 
                                 display_name = md_display_name)
            
        finally:
            # remove the temp file:
            if yml_path and os.path.exists(yml_path):
                os.remove(yml_path)
        
        
        
        
        
        
        
