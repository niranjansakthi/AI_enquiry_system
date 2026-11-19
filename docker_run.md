1. **Build the Docker image:**
   ```powershell
   docker build -t curd-rice-enquiry-app .
   ```

2. **Run the container:**
   Pass your `.env` file using `--env-file .env`:
   ```powershell
   docker run -d `
     --name curd_rice_enquiry_app `
     -p 8000:8000 `
     --env-file .env `
     -v curd_rice_data:/app/data `
     curd-rice-enquiry-app
   ```

3. **Check status & logs:**
   ```powershell
   # See running container
   docker ps

   # Check logs
   docker logs -f curd_rice_enquiry_app
   ```

4. **Stop and remove container:**
   ```powershell
   docker stop curd_rice_enquiry_app
   docker rm curd_rice_enquiry_app
