from flask import Flask, render_template, request, redirect, url_for, session
import psycopg2

app = Flask(__name__)
connect = psycopg2.connect("dbname=tutorial user=postgres password=_____")
cur = connect.cursor()
app.secret_key = 'my_secret_key'

@app.route('/')
def login():
    return render_template("login.html")

@app.route('/register', methods=['POST'])
def register():
    try:
        user_id = request.form["id"].strip()
        password = request.form["password"].strip()
        action = request.form["send"]

        if not user_id or not password:
            return render_template("login.html", message="id와 비밀번호는 최소 1자 이상이어야 합니다.")

        if action == "sign up":
            cur.execute(f"select id from users where id = '{user_id}';")
            if cur.fetchone():
                return render_template("login.html", message="이미 가입되어 있는 id입니다.")
            cur.execute(f"insert into users (id, password, role) values ('{user_id}', '{password}', 'user');")
            connect.commit()
            session['user_id'] = user_id
            return main()

        elif action == "sign in":
            cur.execute(f"select id from users where id = '{user_id}' and password = '{password}';")
            if cur.fetchone():
                session['user_id'] = user_id
                return main()
            return render_template("login.html", message="가입되어 있지 않은 회원입니다. 가입부터 해주세요.")
    except Exception as e:
        connect.rollback()
        return str(e), 500
    
@app.route('/main')
def main():
    try:
        movie_sort_by = session.get('movie_sort', 'latest')
        review_sort_by = session.get('review_sort', 'latest')

        movie_sort_param = request.args.get('movie_sort')
        review_sort_param = request.args.get('review_sort')

        if movie_sort_param:
            movie_sort_by = movie_sort_param
            session['movie_sort'] = movie_sort_by

        if review_sort_param:
            review_sort_by = review_sort_param
            session['review_sort'] = review_sort_by 

        user_id = session.get('user_id')
        
        movie_query = f"""
        select m.id, m.title, m.director, m.genre, m.rel_date, avg(r.ratings) as avg_rating, m.click_count 
        from movies m 
        left join reviews r on m.id = r.mid
        group by m.id """
        if movie_sort_by == 'latest':
            movie_query += "order by m.rel_date desc;"
        elif movie_sort_by == 'genre':
            movie_query += "order by m.genre;"
        elif movie_sort_by == 'ranking':
            movie_query += "order by avg(r.ratings) is null, avg(r.ratings) desc;"
        elif movie_sort_by == 'hottest':
            movie_query += "order by m.click_count desc;"
        cur.execute(movie_query)
        movies_list = cur.fetchall()

        review_query = f"""
        select r.ratings, r.uid as user_name, m.title as movie_title, r.review, r.rev_time, r.mid as movie_id, count(f.opid) as follower_count
        from reviews r
        inner join movies m on r.mid = m.id
        left join ties f on r.uid = f.opid
        where r.uid not in (
            select opid from ties where id = '{user_id}' and tie='mute'
        )
        group by r.ratings, r.uid, m.title, r.review, r.rev_time, r.mid
        """
        if review_sort_by == 'latest':
            review_query += "order by r.rev_time desc;"
        elif review_sort_by == 'title':
            review_query += "order by m.title;"
        elif review_sort_by == 'followers':
            review_query += "order by follower_count desc, r.uid;"  

        cur.execute(review_query)
        reviews_list = cur.fetchall()

        interest_query = f"select movie_id from interests where user_id = '{user_id}';"
        cur.execute(interest_query)
        interest_list = [row[0] for row in cur.fetchall()]
        return render_template('main.html', movies=movies_list, reviews=reviews_list, interest_list=interest_list, user_id=user_id)
    
    except Exception as e:
        connect.rollback()
        return str(e), 500
    
   
@app.route('/toggle_interest/<movie_id>', methods=['POST'])
def toggle_interest(movie_id):
    user_id = session.get('user_id')
    try:
        cur.execute(f"select * from interests where user_id = '{user_id}' and movie_id = '{movie_id}';")
        interest_exists = cur.fetchone()

        if interest_exists:
            cur.execute(f"delete from interests where user_id = '{user_id}' and movie_id = '{movie_id}';")
        else:
            cur.execute(f"insert into interests (user_id, movie_id) values ('{user_id}', '{movie_id}');")

        connect.commit()
    except Exception as e:
        connect.rollback()
        return str(e), 500
    
    return main()

@app.route('/movie_info/<movie_id>')
def movie_info(movie_id):
    try:
        current_user_id = session.get('user_id')

        cur.execute(f"update movies set click_count = click_count + 1 where id = '{movie_id}';")
        connect.commit()

        cur.execute(f"select id, title, director, genre, rel_date, click_count from movies where id = '{movie_id}';")
        movie_details = cur.fetchone()

        cur.execute(f"""
            select round(avg(ratings), 1) as average_rating
            from reviews
            where mid = '{movie_id}';
        """)
        average_rating = cur.fetchone()[0]
            
        cur.execute(f"""
            select ratings, uid, review, rev_time
            from reviews
            where mid = '{movie_id}' and uid not in (
                select opid from ties where id = '{current_user_id}' and tie='mute'
            );
        """)
        reviews = cur.fetchall()

        if movie_details:
            movie = {
                'id': movie_details[0],
                'title': movie_details[1],
                'director': movie_details[2],
                'genre': movie_details[3],
                'rel_date': movie_details[4],
                'average_rating': average_rating,
                'click_count': movie_details[5],
                'reviews': reviews
            }

            return render_template('movie_info.html', movie=movie, current_user_id=current_user_id)
    except Exception as e:
        connect.rollback()
        return str(e), 500 
    

@app.route('/submit_review/<movie_id>', methods=['POST'])
def submit_review(movie_id):
    try:
        user_id = session.get('user_id')
        rating = request.form['rating']
        review = request.form['review']

        cur.execute(f"""
            select * from reviews where uid = '{user_id}' and mid = '{movie_id}';
        """)
        existing_review = cur.fetchone()

        if existing_review:
            cur.execute(f"""
                update reviews
                set ratings = '{rating}', review = '{review}', rev_time = now()
                where uid = '{user_id}' and mid = '{movie_id}';
            """)
        else:
            cur.execute(f"""
                insert into reviews (mid, uid, ratings, review, rev_time)
                values ('{movie_id}', '{user_id}', '{rating}', '{review}', now());
            """)

        connect.commit()
        return redirect(url_for('movie_info', movie_id=movie_id))
    except Exception as e:
        connect.rollback()
        return str(e), 500
    

@app.route('/user_info/<user_id>')
def user_info(user_id):
    try:
        current_user_id = session.get('user_id') 

        cur.execute(f"""
            select r.ratings, m.id, m.title, r.review, r.rev_time
            from reviews r
            join movies m on r.mid = m.id
            where r.uid = '{user_id}';
        """)
        reviews = cur.fetchall()

        cur.execute(f"""
            select m.id, m.title
            from interests i
            join movies m on i.movie_id = m.id
            where i.user_id = '{user_id}';
        """)
        interests = cur.fetchall()

        followed = []
        if current_user_id == user_id: 
            cur.execute(f"""
                select u.id
                from ties t
                join users u on t.opid = u.id
                where t.id = '{user_id}' and t.tie = 'follow';
            """)
            followed = cur.fetchall()

        cur.execute(f"""
            select u.id
            from ties t
            join users u on t.id = u.id
            where t.opid = '{user_id}' and t.tie = 'follow';
        """)
        followers = cur.fetchall()

        muted = []
        if current_user_id == user_id: 
            cur.execute(f"""
                select u.id
                from ties t
                join users u on t.opid = u.id
                where t.id = '{user_id}' and t.tie = 'mute';
            """)
            muted = cur.fetchall()
        return render_template('user_info.html', user_id=user_id, reviews=reviews, interests=interests, followed=followed, followers=followers, muted=muted, current_user_id=current_user_id)
    except Exception as e:
        connect.rollback()
        return str(e), 500
    

@app.route('/follow/<user_id>', methods=['POST'])
def follow_user(user_id):
    try:
        current_user_id = session.get('user_id')

        cur.execute(f"""
            select tie from ties
            where id = '{current_user_id}' and opid = '{user_id}';
        """)
        
        existing_tie = cur.fetchone()

        if existing_tie:
            if existing_tie[0] == 'mute':
                cur.execute(f"""
                    update ties
                    set tie = 'follow'
                    where id = '{current_user_id}' and opid = '{user_id}';
                """)
        else:
            cur.execute(f"""
                insert into ties (id, opid, tie)
                values ('{current_user_id}', '{user_id}', 'follow');
            """)

        connect.commit()
        return user_info(current_user_id)
    except Exception as e:
        connect.rollback()
        return str(e), 500


@app.route('/mute/<user_id>', methods=['POST'])
def mute_user(user_id):
    try:
        current_user_id = session.get('user_id')

        cur.execute(f"""
            select tie from ties
            where id = '{current_user_id}' and opid = '{user_id}';
        """)
        
        existing_tie = cur.fetchone()

        if existing_tie:
            if existing_tie[0] == 'follow':
                cur.execute(f"""
                    update ties
                    set tie = 'mute'
                    where id = '{current_user_id}' and opid = '{user_id}';
                """)
        else:
            cur.execute(f"""
                insert into ties (id, opid, tie)
                values ('{current_user_id}', '{user_id}', 'mute');
            """)

        connect.commit()
        return user_info(current_user_id)
    except Exception as e:
        connect.rollback()
        return str(e), 500



@app.route('/unfollow/<user_id>', methods=['POST'])
def unfollow_user(user_id):
    try:
        current_user_id = session.get('user_id')
        cur.execute(f"delete from ties where id = '{current_user_id}' and opid = '{user_id}' and tie = 'follow';")
        connect.commit()
        return user_info(current_user_id)
    except Exception as e:
        connect.rollback()
        return str(e), 500

@app.route('/unmute/<user_id>', methods=['POST'])
def unmute_user(user_id):
    try:
        current_user_id = session.get('user_id')
        cur.execute(f"delete from ties where id = '{current_user_id}' and opid = '{user_id}' and tie = 'mute';")
        connect.commit()
        return user_info(current_user_id)
    except Exception as e:
        connect.rollback()
        return str(e), 500
    
@app.route('/add_movie', methods=['POST'])
def add_movie():
    try:
        title = request.form['title']
        director = request.form['director']
        genre = request.form['genre']
        rel_date = request.form['rel_date']

        cur.execute("select max(id) from movies;")
        max_id = cur.fetchone()[0]
        new_id = int(max_id) + 1 if max_id is not None else 1

        cur.execute(f"insert into movies (id, title, director, genre, rel_date) values ('{new_id}', '{title}', '{director}', '{genre}', '{rel_date}');")
        connect.commit()
        return redirect(url_for('user_info', user_id=session.get('user_id')))
    except Exception as e:
        connect.rollback()
        return str(e), 500
 
if __name__ == "__main__":
    app.run(port=8000, debug=True)
