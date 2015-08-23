#! coding=utf8
from flask import Flask, request, session, g, redirect, url_for, abort, \
    render_template, flash, jsonify, json
from mongo_single import Mongo
import time
import os
from functions import get_project_list, md5
from helper import GlobalHelper
from spider_for_test import test_run

# from gevent import monkey
# monkey.patch_socket()  # fixme patch_all 会影响跨进程通讯或者异步抓取 1/2

from gevent.wsgi import WSGIServer
from flask.ext.compress import Compress

app = Flask(__name__)
Compress(app)

app.config.update(dict(
    SECRET_KEY='development key',
))


def get_template(template_path):
    with open(os.path.dirname(os.path.abspath(__file__)) + '/templates/' + template_path) as f:  # todo 后期上缓存
        return f.read()


@app.errorhandler(404)
def page_not_found(error):
    return redirect('/project')


@app.route('/')
def index():
    return redirect('/main.html')


@app.route('/<path>')
@app.route('/project/<path>')
@app.route('/project/task/<path>')
@app.route('/project/edit/<path>')
@app.route('/project/add/<path>')
@app.route('/slave/task/<path>')
@app.route('/slave/result/<path>')
@app.route('/project/result/<path>')
def default(path):
    """
    首次全新请求(即不经过angular的请求)url地址的route规则
    """
    return get_template('main.html')


@app.route('/component/<page>')
@app.route('/component/task/<page>')
def page(page):
    return get_template('component/' + page + '.html')


@app.route('/api/test')
def api_test():
    print GlobalHelper.get('salve_record')
    # time.sleep(10)
    return jsonify({'fd': 1})


@app.route('/api/slave')
def api_slave():
    return jsonify(GlobalHelper.get('salve_record') or {})


@app.route('/api/project')
def get_projects():
    project_dict = {}
    for project in get_project_list():
        project_dict[project['name']] = {
            'name': project['name'],
            'static': project['static'],
            'queue_len': Mongo.get()['queue_' + project['name']].count(),
            'parsed_len': Mongo.get()['parsed_' + project['name']].count(),
            'result_len': Mongo.get()['result_' + project['name']].count(),
        }

    return jsonify(project_dict)


@app.route('/api/project/<name>')
def get_project_by_name(name):
    res = list(Mongo.get().projects.find({'name': name}, {'_id': 0}))
    if not res:
        return jsonify({})
    return jsonify(res[0])


@app.route('/api/project/save', methods=['POST'])
def save_project():
    form_data = json.loads(request.data)  # todo 需要验证表单数据

    exists_project = list(Mongo.get()['projects'].find({'name': form_data['name']}, {'_id': 1, 'add_time': 1}).limit(1))

    if 'edit' not in form_data and exists_project:
        return jsonify({'success': False, 'msg': '计划名称已经存在!'})

    # 新增计划或更新计划
    data = {
        'name': form_data['name'],
        'init_url': form_data['init_url'],
        'desc': form_data['desc'] if 'desc' in form_data else '',
        'code': form_data['code'],
        'static': '测试中',
        'update_time': int(time.time()),
        'add_time': exists_project[0]['add_time'] if exists_project else int(time.time()),
    }
    Mongo.get()['projects'].update({'name': form_data['name']}, data, True)

    # 当时新计划时的初始化
    if 'edit' not in form_data:
        Mongo.get()['queue_' + form_data['name']].insert(
            {
                'url': form_data['init_url'],
                'url_md5': md5(form_data['init_url']),
                'flag_time': 0,
                'add_time': int(time.time()),
                'slave_ip': '0.0.0.0'
            })

        # 在没创建集合前设置索引mongodb会自动创建该集合并赋索引
        Mongo.get()['parsed_' + form_data['name']].ensure_index('url_md5', unique=True)
        Mongo.get()['queue_' + form_data['name']].ensure_index('url_md5', unique=True)

    return jsonify({'success': True, 'msg': '保存成功!'})


@app.route('/api/slave/<ip>')
def get_slave_tasks(ip):
    res = []
    for project in get_project_list():
        for doc in Mongo.get()['parsed_' + project['name']].find({'slave_ip': ip}).sort('_id', -1).limit(100):
            del doc['_id']
            res.append(doc)
    return json.dumps(res)


@app.route('/api/task/<project_name>')
def get_project_tasks(project_name):
    res = []
    for doc in Mongo.get()['parsed_' + project_name].find().sort('_id', -1).limit(100):
        del doc['_id']
        res.append(doc)
    return json.dumps(res)


@app.route('/api/result/<project_name>')
def get_results(project_name):
    res = []
    for doc in Mongo.get()['result_' + project_name].find().sort('_id', -1).limit(100):
        del doc['_id']
        res.append(doc)
    return json.dumps(res)


@app.route('/api/project/exec_test', methods=['POST'])
def exec_test():
    form_data = json.loads(request.data)  # todo 需要验证表单数据

    result = test_run(form_data)
    if 'error' in result:
        return json.dumps({'success': False, 'msg': result['error'], 'result': {'stdout': result['stdout']}})

    result['urls'] = result['urls'][::-1]

    return json.dumps({'success': True, 'msg': '成功', 'result': result})


def web_start(dd):
    """
    当service.py为入口时会调用这里
    """
    GlobalHelper.init(dd)
    http_server = WSGIServer(('0.0.0.0', 80), app)
    http_server.serve_forever()


if __name__ == '__main__':
    """
    当前文件为入口时会调用这里
    """
    app.run('0.0.0.0', 80, debug=True, threaded=True)