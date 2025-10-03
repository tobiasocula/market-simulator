import MyContext from "./context.jsx";
import { useState, useContext } from "react";
import GeneralInfo from "./GeneralInfo.jsx";


function OB(data) {
    //console.log('data:', data.data);
    if (!Array.isArray(data.data)) return (
        <table border="1">
        <thead>
            <tr>
            <th>Price</th>
            <th>Volume</th>
            <th>Time</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td></td>
                <td></td>
                <td></td>
            </tr>
        </tbody>
        </table>
    );
    // data is an array of arrays
    //console.log('NOT NULL;')
    return (
    <table border="1">
      <thead>
        <tr>
          <th>Price</th>
          <th>Volume</th>
          <th>Time</th>
        </tr>
      </thead>
      <tbody>
        {data.data.map((row, i) => (
          <tr key={i}>
            {row.map((cell, j) => (
              <td key={j}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}


function OrderBooks() {
    const {streamedData} = useContext(MyContext);
    const [selectedExpiry, setSelectedExpiry] = useState(0);
    const [selectedStrike, setSelectedStrike] = useState(0);

    function findExpiryIndex(exp) {
        for (let i=0; i<streamedData.expiries.length; i++) {
            if (streamedData.expiries[i] === exp) return i;
        }
    }

    function findStrikeIndex(str) {
        console.log('find strike:', str);
        console.log('strikes:', streamedData.strikes);
        for (let i=0; i<streamedData.strikes.length; i++) {
            console.log('current:', streamedData.strikes[i]);
            if (streamedData.strikes[i] === str) return i;
        }
    }

    

    //console.log('sd:', streamedData.obs);
    console.log('selected strike:', selectedStrike);

    return (
        <>
        <div style={{display: "flex", flexDirection: "column", alignItems: "center", gap: "10px"}}>
            <GeneralInfo/>

            {streamedData && (

            <div style={{
                display: "flex",
                justifyContent: "center",
            }}>
                <select id="simpleDropdown" name="simpleDropdown"
                value={streamedData.expiries[selectedExpiry]}
                onChange={(e) => setSelectedExpiry(findExpiryIndex(e.target.value))}>
                    {streamedData.expiries.map((exp, i) => 
                        <option key={i} value={exp}>{exp}</option>
                    )}
                </select>

                <select id="simpleDropdown" name="simpleDropdown"
                value={streamedData.strikes[selectedStrike]}
                onChange={(e) => setSelectedStrike(findStrikeIndex(Number(e.target.value)))}>
                    {streamedData.strikes.map((str, i) => 
                        <option key={i} value={str}>{str}</option>
                    )}
                </select>

            </div>

                )}
        </div>
        

        {!streamedData || !streamedData.obs[selectedExpiry] ? <div style={{display: "flex", flexDirection: "column", alignItems: "center"}}
        >No data here yet</div> : (
            <div>
                {!streamedData.obs[selectedExpiry].data[selectedStrike] ? <div>failed strike</div> : (
                    <div style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "10px"
                    }}> 
                        <div style={{display: "flex", flexDirection: "column", gap: "10px", alignItems: "center"}}>
                            <div>Calls</div>
                                <div style={{
                                        display: "flex", gap: "10px", justifyContent: "space-evenly"
                                    }}>
                                    <div style={{display: "flex", flexDirection: "column"}}>
                                        <div>Buy table</div>
                                        <OB data={streamedData.obs[selectedExpiry].data[selectedStrike].ob.calls_bids} />    
                                    </div>
                                    <div style={{display: "flex", flexDirection: "column"}}>
                                        <div>Sell table</div>
                                        <OB data={streamedData.obs[selectedExpiry].data[selectedStrike].ob.calls_asks} />    
                                    </div>
                                </div>
                            </div>
                        <div style={{display: "flex", flexDirection: "column", gap: "10px", alignItems: "center"}}>
                            <div>Puts</div>
                                <div style={{
                                    display: "flex", gap: "10px", justifyContent: "space-evenly"
                                }}>
                                    <div style={{display: "flex", flexDirection: "column"}}>
                                        <div>Buy table</div>
                                        <OB data={streamedData.obs[selectedExpiry].data[selectedStrike].ob.puts_bids} />    
                                    </div>
                                    <div style={{display: "flex", flexDirection: "column"}}>
                                        <div>Sell table</div>
                                        <OB data={streamedData.obs[selectedExpiry].data[selectedStrike].ob.puts_asks} />    
                                    </div>
                                </div>
                        </div>
                    </div>
                )}
            </div>
        )}

   

        </>
        
    );
    }

export default OrderBooks;