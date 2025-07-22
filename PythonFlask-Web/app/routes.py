from datetime import datetime, timezone
from urllib.parse import urlsplit
from flask import render_template, flash, redirect, url_for, request
from flask_login import login_user, logout_user, current_user, login_required
import sqlalchemy as sa
from app import app, db
from app.forms import LoginForm, RegistrationForm, EditProfileForm, PostForm, SearchForm
from app.models import User, Post
import bleach


@app.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.now(timezone.utc)
        db.session.commit()


@app.route('/', methods=['GET', 'POST'])
@app.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    form = PostForm()
    if form.validate_on_submit():
        clean_body = bleach.clean(form.post.data, tags=[], strip=True)
        post = Post(body=clean_body, author=current_user)
        db.session.add(post)
        db.session.commit()
        flash('Your post is now live!')
        return redirect(url_for('index'))
    return render_template("index.html", title='Home Page', form=form)


@app.route('/explore')
@login_required
def explore():
    query = sa.select(Post).order_by(Post.timestamp.desc())
    posts = db.session.scalars(query).all()
    return render_template('explore.html', title='Explore', posts=posts)


@app.route('/posts/<int:id>')
@login_required
def post(id):
    post = Post.query.get_or_404(id)
    return render_template('_post.html', post=post) 


@app.route('/posts/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_post(id):
    post = Post.query.get_or_404(id)
    form = PostForm()
    if form.validate_on_submit():
        clean_body = bleach.clean(form.post.data, tags=[], strip=True)
        post.body = clean_body

        db.session.add(post)
        db.session.commit()
        flash('Your post has been updated!')
        return redirect(url_for('post', id=post.id))
    
    if(current_user.id == post.user_id):
        form.post.data = post.body
        return render_template('edit_post.html', form=form)
    else:
        flash('You are not authorized to edit this post...')
        return redirect(url_for('explore'))


@app.route('/posts/delete/<int:id>')
@login_required
def delete_post(id):
    post_to_delete = Post.query.get_or_404(id)

    try:
        db.session.delete(post_to_delete)
        db.session.commit()
        flash('Your post was deleted!')

        posts = Post.query.order_by(Post.timestamp)
        return render_template('explore.html', posts=posts)
    except:
        flash('Whoops, there was a problem deleting post, try again!')

        posts = Post.query.order_by(Post.timestamp)
        return render_template('explore.html', posts=posts)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(
            sa.select(User).where(User.username == form.username.data))
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        if not user.is_approved:
            flash('Your account is pending approval')
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or urlsplit(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    return render_template('login.html', title='Sign In', form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            is_approved=False,      
            role='user'              
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please wait for admin approval.')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)



@app.route('/user/<username>')
@login_required
def user(username):
    user = db.first_or_404(sa.select(User).where(User.username == username))
    posts = Post.query.filter(Post.user_id==current_user.id)
    return render_template('user.html', user=user, posts=posts)


@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm(current_user.username)
    if form.validate_on_submit():
        current_user.username = form.username.data

        clean_about_me = bleach.clean(form.about_me.data, tags=[], attributes={}, strip=True)
        current_user.about_me = clean_about_me
        db.session.commit()
        flash('Your changes have been saved.')
        return redirect(url_for('edit_profile'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.about_me.data = current_user.about_me
    return render_template('edit_profile.html', title='Edit Profile',
                           form=form)


@app.context_processor
def base():
    form = SearchForm()
    return dict(form=form)


@app.route('/search', methods=["POST"])
@login_required
def search():
    form = SearchForm()
    posts = Post.query
    if form.validate_on_submit():
        searched = bleach.clean(form.searched.data, tags=[], strip=True)

        posts = posts.filter(Post.body.like('%' + searched + '%'))
        posts = posts.order_by(Post.timestamp).all()
        return render_template('search.html', form=form, 
                               searched = searched, posts=posts)
    
    flash('You must enter a value in the search box')
    return redirect(url_for('explore'))


def admin_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('You do not have permission to access this page')
            return redirect(url_for('explore')) 
        return func(*args, **kwargs)
    return wrapper

@app.route('/admin/users')
@login_required
@admin_required
def manage_users():
    users = User.query.all()
    return render_template('admin/manage_users.html', users=users)

@app.route('/admin/approve/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    flash(f'User {user.username} has been approved.')
    return redirect(url_for('manage_users'))

@app.route('/admin/set-role/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def set_role(user_id):
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    if user.id == current_user.id:
        flash('You cannot change your own role')
        return redirect(url_for('manage_users'))

    if new_role in ['user', 'admin']:
        user.role = new_role
        db.session.commit()
        flash(f"{user.username}'s role updated to {new_role}.")
    else:
        flash('Invalid role.')
    return redirect(url_for('manage_users'))