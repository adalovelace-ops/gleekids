FROM php:8.2-apache

# 1. Install MySQL Extensions
RUN docker-php-ext-install mysqli pdo pdo_mysql

# 2. Fix Permissions (Run as root)
RUN sed -i 's/APACHE_RUN_USER=www-data/APACHE_RUN_USER=root/g' /etc/apache2/envvars
RUN sed -i 's/APACHE_RUN_GROUP=www-data/APACHE_RUN_GROUP=root/g' /etc/apache2/envvars

# 3. FIX: Increase Upload Size Limits
RUN echo "upload_max_filesize = 50M" > /usr/local/etc/php/conf.d/uploads.ini
RUN echo "post_max_size = 50M" >> /usr/local/etc/php/conf.d/uploads.ini

# 4. Fix DirectoryIndex
RUN echo "DirectoryIndex index.php index.html" > /etc/apache2/conf-available/custom-index.conf && a2enconf custom-index

WORKDIR /var/www/html