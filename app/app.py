from flask import Flask, render_template, request, url_for, flash, redirect, session
from flask_paginate import Pagination, get_page_args
from werkzeug.exceptions import abort
import pyspark
from pyspark.sql import SQLContext
from pyspark.sql import HiveContext
from pyspark.sql import functions as f
from cassandra.cluster import Cluster
import pandas as pd

def get_db_connection():
    cluster = Cluster()
    session = cluster.connect("dsci551")
    return session

def get_spark_table():
    sc = pyspark.SparkContext()
    sqlContext = pyspark.SQLContext(sc)
    hc = HiveContext(sc)

    conn = get_db_connection()
    rows = conn.execute('select * from cves')
    df = sqlContext.createDataFrame(pd.DataFrame(list(rows)))
    df.registerTempTable('cves')

    conn.shutdown()

    return hc

hc = get_spark_table()

def get_post(cve_id):
    conn = get_db_connection()
    post = conn.execute("select id,attack_complexity,attack_vector,cast(base_score as float) as base_score,base_severity,\
            description,lastmodified_date,published_date,references FROM cves WHERE id = '{}'".format(cve_id)).one()
    conn.shutdown()
    if post is None:
        abort(404)
    return post

def get_references(post):
    references = post.references.split(';')
    return references

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
            query = "select id,description,published_date,base_severity,base_score,ROW_NUMBER() over (order by published_date desc) as RowNum from cves where "
            where_list = list(filter(None,[id_where,expr,date_where,score_where]))
            where = " and ".join(where_list)
            query = query+where
            queries.append(query)
    else:
        query = "select id,description,published_date,base_severity,base_score,ROW_NUMBER() over (order by published_date desc) as RowNum from cves where "
        where_list = list(filter(None,[id_where,date_where,score_where]))
        where = " and ".join(where_list)
        query = query+where
        return [query]
            
    return queries

def get_data(queries,offset,limit):
    data = []
    count = 0
    i = 0
    for query in queries.values():
        count += hc.sql(query).count()
        query = "with result as ({}) select id,description,published_date,round(base_score,1) as base_score,base_severity \
            from result".format(query)
        if i == 0:
            data = hc.sql(query)
            i += 1
        else:
            results = hc.sql(query)
            data = data.union(results)

    avg_score = data.replace(float('nan'),None).select('base_score').agg(f.round(f.mean("base_score"),1).alias("average_base_score")).collect()[0]["average_base_score"]
    min_score = data.replace(float('nan'),None).select('base_score').agg(f.round(f.min("base_score"),1).alias("min_base_score")).collect()[0]["min_base_score"]
    max_score = data.replace(float('nan'),None).select('base_score').agg(f.round(f.max("base_score"),1).alias("max_base_score")).collect()[0]["max_base_score"]
    stats = {"avg_score": avg_score, "min_score": min_score, "max_score": max_score}

    return data.collect(),count,stats

app = Flask(__name__)
app.config['SECRET_KEY'] = 'AbLAVBIOFzuc7QCgTC4d'

@app.route('/', methods=('GET', 'POST'))
def index():
    if request.method == 'POST':
        cve_id = request.form['cve_id']
        return redirect(url_for('post', cve_id=cve_id))
    posts = hc.sql("select * from cves order by published_date desc limit 10").collect()
    severe_posts = hc.sql("select id,round(base_score,2) as base_score,base_severity from cves where published_date > '2021-02-04' and attack_vector is not null order by base_score desc limit 10").collect()

    return render_template('home.html', posts=posts, severe_posts=severe_posts)

@app.route('/<cve_id>')
def post(cve_id):
    post = get_post(cve_id)
    if post.base_score != None:
        base_score = round(post.base_score,1)
    else:
        base_score = 'N/A'
    references = get_references(post)
    return render_template('post.html', post=post, references=references, base_score=base_score)

@app.route('/search', methods=('GET', 'POST'))
def search():
    if request.method == 'POST':
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

@app.route('/search-results')
def search_results():
    page, per_page, offset = get_page_args()
    queries = session.get('queries')

    data,total_records,stats = get_data(queries,offset,per_page)
    cves = data[offset:offset+per_page]
    pagination = Pagination(page=page,per_page=per_page,offset=offset,total=total_records,record_name='cves', css_framework='bootstrap4')

    return render_template('results.html',cves=cves,pagination=pagination,stats=stats)

if __name__ == '__main__':
    app.run()