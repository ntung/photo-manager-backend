function updateQueryParam(key, value) {
    const url = new URL(window.location.href);

    if (value) {
        url.searchParams.set(key, value);
    } else {
        url.searchParams.delete(key); // Remove it if value is empty
    }

    // Use replaceState to avoid "spamming" the back button history
    window.history.replaceState({}, '', url);
}


function previousPage() {
    let currentPage = -1;
    // Example URL: https://example.com/?user=gemini&page=2
    const queryString = window.location.search;
    const urlParams = new URLSearchParams(queryString);

    // Get a specific value
    const user = urlParams.get('user'); // "gemini"
    const page = urlParams.get('page'); // "2"

    // Check if a parameter exists
    if (urlParams.has('page')) {
        console.log("The previous page is " + page);
        currentPage = parseInt(page);
    } else {
        console.log("Get the initial value for the page!");
    }
    return currentPage;
}