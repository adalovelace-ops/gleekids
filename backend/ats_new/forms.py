from django import forms
from .models import Applicant

class ApplicantRegistrationForm(forms.ModelForm):
    confirm_password = forms.CharField(widget=forms.PasswordInput())

    class Meta:
        model = Applicant
        fields = [
            'first_name', 'middle_name', 'last_name', 'email', 'phone', 
            'country', 'date_of_birth', 'address', 'city', 'state', 
            'zip_code', 'referral', 'password', 'resume', 'video'
        ]

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password != confirm_password:
            raise forms.ValidationError("Passwords do not match")
        
        return cleaned_data
