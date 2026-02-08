@app.route('/manual-resolve', methods=['POST'])
@login_required
def manual_resolve():
    url = request.form.get('test_url')
    settings = Settings.query.first()
    
    if url:
        try:
            # Call the new VERBOSE function
            results = scraper_logic.resolve_all_mirrors_verbose(
                url, 
                settings.mediator_domain, 
                settings.hubdrive_domain
            )
            
            # Refresh dashboard data to render the page correctly
            status = BotStatus.query.first()
            logs = Logs.query.order_by(Logs.timestamp.desc()).limit(50).all()
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            total = History.query.count()
            
            # Pass 'manual_result' to the template
            return render_template('dashboard.html', 
                                   settings=settings, 
                                   status=status, 
                                   logs=logs, 
                                   cpu=cpu, ram=ram, 
                                   total=total,
                                   manual_result=results) # <--- THIS IS KEY
        except Exception as e:
            flash(f"Error resolving: {e}")
            
    return redirect(url_for('dashboard'))
