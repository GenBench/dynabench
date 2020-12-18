# Copyright (c) Facebook, Inc. and its affiliates.

import json
from urllib.parse import parse_qs

import bottle

import common.auth as _auth
import common.helpers as util
from common.logging import logger
from models.context import Context, ContextModel
from models.round import RoundModel
from models.task import TaskModel
from models.user import UserModel


@bottle.get("/contexts/<tid:int>/<rid:int>")
@bottle.get("/contexts/<tid:int>/<rid:int>/min")
def getContext(tid, rid):
    query_dict = parse_qs(bottle.request.query_string)
    tags = None
    if "tags" in query_dict and len(query_dict["tags"]) > 0:
        tags = query_dict["tags"][0].split("|")

    return _getContext(tid, rid, tags=tags)


@bottle.get("/contexts/<tid:int>/<rid:int>/uniform")
@_auth.requires_auth_or_turk
def getUniformContext(credentials, tid, rid):
    query_dict = parse_qs(bottle.request.query_string)
    tags = None
    if "tags" in query_dict and len(query_dict["tags"]) > 0:
        tags = query_dict["tags"][0].split("|")

    return _getContext(tid, rid, "uniform", tags)


def _getContext(tid, rid, method="min", tags=None):
    rm = RoundModel()
    round = rm.getByTidAndRid(tid, rid)
    c = ContextModel()
    if method == "uniform":
        context = c.getRandom(round.id, n=1, tags=tags)
    elif method == "min":
        context = c.getRandomMin(round.id, n=1, tags=tags)
    if not context:
        bottle.abort(500, f"No contexts available ({round.id})")
    context = context[0].to_dict()
    return util.json_encode(context)


@bottle.post("/contexts/upload")
@_auth.requires_auth
def do_upload(credentials):
    """
    Upload a contexts file for the current round
    and save the contexts to the contexts table
    :param credentials:
    :return: success info
    """
    u = UserModel()
    user_id = credentials["id"]
    user = u.get(user_id)
    if not user:
        logger.error("Invalid user detail for id (%s)" % (user_id))
        bottle.abort(404, "User information not found")

    task_id = bottle.request.forms.get("taskId")
    if not user.admin and not (
        (task_id, "owner") in [(perm.tid, perm.type) for perm in user.task_permissions]
    ):
        bottle.abort(403, "Access denied (you are not an admin or owner of this task)")

    upload = bottle.request.files.get("file")

    try:
        parsed_upload_data = [
            json.loads(line) for line in upload.file.read().decode("utf-8").splitlines()
        ]
        for context_info in parsed_upload_data:
            if (
                "text" not in context_info
                or "tag" not in context_info
                or "metadata" not in context_info
            ):
                bottle.abort(400, "Upload valid contexts file")

    except Exception as ex:
        logger.exception(ex)
        bottle.abort(400, "Upload valid contexts file")

    r_realid = TaskModel().getWithRound(task_id)["round"]["id"]
    contexts_to_add = []
    for context_info in parsed_upload_data:
        c = Context(
            r_realid=r_realid,
            context=context_info["text"],
            metadata_json=json.dumps(context_info["metadata"]),
            tag=context_info["tag"],
        )
        contexts_to_add.append(c)

    u.dbs.bulk_save_objects(contexts_to_add)
    u.dbs.commit()
    return util.json_encode({"success": "ok"})
