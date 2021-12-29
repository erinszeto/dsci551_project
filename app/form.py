from flask import Flask, redirect, url_for, request,render_template
app = Flask(__name__)

@app.route('/success/<name>')
def success(name):
   return 'welcome %s' % name

@app.route('/form',methods = ['POST', 'GET'])
def login():
   if request.method == 'POST':
        user = request.form['keyword']
        return redirect(url_for('success',name = user))
#    else:
#       user = request.args.get('keyword')
#        return redirect(url_for('success',name = user))

   return render_template('form.html')

if __name__ == '__main__':
   app.run(debug = True)