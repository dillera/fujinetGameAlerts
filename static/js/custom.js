console.log



function validatePhoneNumber() {
    var inputElement = document.getElementById('phone_number');
    var phoneNumber = inputElement.value;

    if (phoneNumber) {
        var isValid = window.libphonenumber.isValidNumberForRegion(phoneNumber, 'US');
        if (!isValid) {
            alert('Invalid phone number. Please enter a valid US phone number for SMS or use Whats App.');
            inputElement.value = '';
        }
    }
}


function validateWhatsAppNumber() {
  var inputElement = document.getElementById('whatsapp_number');
  var whatsappNumber = inputElement.unmaskedValue;

  if (whatsappNumber) {
    var isValid = window.libphonenumber.isValidNumberForRegion(whatsappNumber, 'GB'); // 'GB' for the United Kingdom
    if (!isValid) {
      alert('Invalid number. Please enter a valid international WhatsApp number.');
      inputElement.value = ''; // Clear the input if it's not valid
    }
  }
}



function confirmDeletion() {
      return confirm('Are you sure you want to delete your info and all data?');
    }
