from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('applications/', views.application_list, name='application_list'),
    path('applications/add/', views.add_application, name='add_application'),
    path('applications/<int:pk>/', views.application_detail, name='application_detail'),
    path('applications/<int:pk>/edit/', views.edit_application, name='edit_application'),
    path('applications/<int:pk>/delete/', views.delete_application, name='delete_application'),
    path('applications/<int:pk>/status/', views.update_status, name='update_status'),
    path('applications/<int:pk>/resume/', views.view_resume, name='view_resume'),
    path('applications/<int:pk>/resume/download/', views.download_resume, name='download_resume'),
    path('applications/<int:pk>/resume/view/', views.serve_resume, name='serve_resume'),
    path('logout/', views.logout_view, name='logout'),
    path('logo/<str:company>/', views.company_logo, name='company_logo'),
    path('scrape-job/', views.scrape_job, name='scrape_job'),
    path('set-timezone/', views.set_timezone, name='set_timezone'),
    path('settings/', views.user_settings, name='user_settings'),
]
# Already imported views above
