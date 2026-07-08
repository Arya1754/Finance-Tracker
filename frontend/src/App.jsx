import { useState, useEffect } from 'react'

function App() {
  const [portfolio, setPortfolio] = useState({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('http://localhost:5000/api/portfolio')
      .then(response => response.json())
      .then(data => {
        setPortfolio(data)
        setLoading(false)
      })
      .catch(error => console.error("Error fetching data:", error))
  }, [])

  return (
    <div className="min-h-screen bg-slate-50 p-8 font-sans">
      <div className="max-w-4xl mx-auto">
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-slate-800">Family Portfolio Tracker</h1>
          <p className="text-slate-500 mt-1">Live updates and predictive insights</p>
        </header>
        
        {loading ? (
          <div className="flex justify-center items-center h-40">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {Object.entries(portfolio).map(([ticker, data]) => (
              <div key={ticker} className="bg-white rounded-xl shadow-sm border border-slate-100 p-6 hover:shadow-md transition-shadow">
                
                {/* Header: Ticker Name & Type Badge */}
                <div className="flex justify-between items-center mb-4">
                  <h2 className="font-bold text-xl text-slate-700">{ticker}</h2>
                  <span className="text-xs font-semibold px-2 py-1 bg-indigo-50 text-indigo-600 rounded-full">
                    {/* We now use the 'type' sent directly from our Python backend! */}
                    {data.type ? data.type.toUpperCase() : 'EQUITY'}
                  </span>
                </div>
                
                {data.status === 'success' ? (
                  <div>
                    {/* Current Price */}
                    <p className="text-3xl font-black text-slate-900 mb-1">
                      ₹{data.price.toLocaleString('en-IN')}
                    </p>
                    
                    {/* --- AI PREDICTION UI --- */}
                    {data.prediction && (
                      <div className={`mt-3 p-3 rounded-lg border ${data.prediction > data.price ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
                        <p className="text-xs text-slate-500 font-semibold uppercase tracking-wider mb-1">AI Prediction (Tomorrow)</p>
                        <div className="flex items-center gap-2">
                          <span className={`text-lg font-bold ${data.prediction > data.price ? 'text-green-700' : 'text-red-700'}`}>
                            ₹{data.prediction.toLocaleString('en-IN')}
                          </span>
                          
                          {/* Arrow indicator */}
                          {data.prediction > data.price ? (
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-green-600" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M12 7a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0V8.414l-4.293 4.293a1 1 0 01-1.414 0L8 10.414l-4.293 4.293a1 1 0 01-1.414-1.414l5-5a1 1 0 011.414 0L10.586 10l3.293-3.293H12z" clipRule="evenodd" /></svg>
                          ) : (
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-red-600" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M12 13a1 1 0 100 2h5a1 1 0 001-1V9a1 1 0 10-2 0v2.586l-4.293-4.293a1 1 0 00-1.414 0L8 9.586 3.707 5.293a1 1 0 00-1.414 1.414l5 5a1 1 0 001.414 0L10.586 10l3.293 3.293H12z" clipRule="evenodd" /></svg>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-red-500 text-sm bg-red-50 p-3 rounded-lg">Failed to load data. {data.message}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default App