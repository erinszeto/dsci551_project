from flask import Flask, render_template, request, url_for, flash, redirect, session
from flask_paginate import Pagination, get_page_args
from werkzeug.exceptions import abort
import pyspark
from pyspark.sql import SQLContext
from pyspark.sql import HiveContext
from cassandra.cluster import Cluster

def get_spark_table():
    sc = pyspark.SparkContext()
    sqlContext = pyspark.SQLContext(sc)
    hc = HiveContext(sc)

    df = sqlContext.read.parquet('/Users/erinszeto/Documents/USC/Spring2021/DSCI551/project/cassandra/spark-warehouse/cves')
    df.registerTempTable('cves')
    return hc

hc = get_spark_table()

def get_db_connection():
    cluster = Cluster()
    session = cluster.connect("dsci551")
    return session

def get_post(cve_id):
    conn = get_db_connection()
    post = conn.execute("SELECT * FROM cves WHERE id = '{}'".format(cve_id)).one()
    conn.shutdown()
    if post is None:
        abort(404)
    return post

def get_desc_where(keyword):
    desc_where = []
    keyword = keyword.lower()
    expressions = ['{}%','%{}','%{}%']

    for expr in expressions:
        query = "lower(description) like '{}'".format(expr.format(keyword))
        desc_where.append(query)

    return desc_where

def get_all_queries(cve_id,keyword,start_date,end_date,start_score,end_score):
    if cve_id != "":
        id_where = "id = {}".format(cve_id)
    else:
        id_where = ""

    if keyword != "":
        desc_where = get_desc_where(keyword)
    else:
        desc_where = ""
        
    if start_date != "" and end_date != "":
        date_where = "published_date >= '{}' and published_date <= '{}'".format(start_date,end_date)
    elif start_date != "" and end_date == "":
        date_where = "published_date >= '{}'".format(start_date)
    elif start_date == "" and end_date != "":
        date_where = "published_date <= '{}'".format(end_date)
    else:
        date_where = ""

    if start_score != "" and end_score != "":
        score_where = "base_score >= {} and base_score <= {}".format(start_score,end_score)
    elif start_score != "" and end_score == "":
        score_where = "base_score >= {}".format(start_score)
    elif start_score == "" and end_score != "":
        score_where = "base_score <= {}".format(end_score)
    else:
        score_where = ""

    queries = get_query(id_where,desc_where,date_where,score_where)
    return queries

def get_query(id_where,desc_where,date_where,score_where):
    queries = []
    
    if desc_where != "":
        for expr in desc_where:
            query = "select id,description,published_date,base_score,ROW_NUMBER() over (order by published_date desc) as RowNum from cves where "
            where_list = list(filter(None,[id_where,expr,date_where,score_where]))
            where = " and ".join(where_list)
            query = query+where
            queries.append(query)
    else:
        query = "select id,description,published_date,base_score,ROW_NUMBER() over (order by published_date desc) as RowNum from cves where "
 #       query = "select id,description,published_date,base_score from cves where "
        where_list = list(filter(None,[id_where,date_where,score_where]))
        where = " and ".join(where_list)
        query = query+where
        return [query]
            
    return queries

def get_data(queries,offset,limit):
    data = []
    count = 0
    for query in queries.values():
        count += hc.sql(query).count()
        query = "with result as ({}) select id,description,published_date,base_score \
            from result where RowNum >= {} and RowNum < {}".format(query,offset,(offset+limit))
#        query = query + " offset {} limit {}".format(offset,limit)
        data = data + hc.sql(query).collect()

    return data,count

app = Flask(__name__)
app.config['SECRET_KEY'] = 'AbLAVBIOFzuc7QCgTC4d'

@app.route('/')
def index():
    conn = get_db_connection()
    posts = conn.execute('SELECT * FROM cves LIMIT 10')
    conn.shutdown()
    return render_template('index.html',posts=posts)

@app.route('/<cve_id>')
def post(cve_id):
    post = get_post(cve_id)
    return render_template('post.html', post=post)

@app.route('/search', methods=('GET', 'POST'))
def search():
    if request.method == 'POST':
        # session['formdata'] = request.form
        cve_id = request.form['cve_id']
        keyword = request.form['keyword']
        start_date = request.form['start_date']
        end_date = request.form['end_date']
        start_score = request.form['start_score']
        end_score = request.form['end_score']

        queries = get_all_queries(cve_id,keyword,start_date,end_date,start_score,end_score)
        queries_dict = {i:queries[i] for i in range(len(queries))}

        session['queries'] = queries_dict

        return redirect(url_for('search_results'))

    return render_template('search.html')


## cve_id,keyword,start_date,end_date,start_score,end_score

# @app.route('/search-results')
# def search_results():
#     # formdata = session.get('formdata')
#     queries = session.get('queries')
#     page_no = int(request.args.get('page',1))
#     results_per_page = 10
#     offset = (page_no-1)*results_per_page

#     data = get_data(queries,offset,results_per_page)

#     return render_template('index.html',posts=data)

@app.route('/search-results')
def search_results():
    page, per_page, offset = get_page_args()
    queries = session.get('queries')
#    page_no = int(request.args.get('page',1))
#    results_per_page = 10
#    offset = (page_no-1)*results_per_page

    data,total_records = get_data(queries,offset,per_page)
    cves = data[offset:offset+per_page]
    pagination = Pagination(page=page,per_page=per_page,offset=offset,total=total_records,record_name='cves')

    return render_template('search_results.html',cves=cves,pagination=pagination)

if __name__ == '__main__':
    app.run()