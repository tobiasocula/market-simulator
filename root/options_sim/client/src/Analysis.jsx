import MyContext from "./context.jsx";
import { useState, useContext } from "react";
import GeneralInfo from "./GeneralInfo.jsx";


function Heatmap({ matrix, rowLabels = [], colLabels = [], stdRange = true }) {
  // Find min and max values in the matrix for color scaling
  let min;
  let max;
  if (!stdRange) {
    const values = matrix.flat();
    min = Math.min(...values);
    max = Math.max(...values);
  }

  function valueToColor(value, min = null, max = null) {
    if (min === null) {
      const r = Math.round(255 * value);
      const g = Math.round(255 * (1 - value));
      return `rgb(${r},${g},0)`;
    }
    const ratio = (value - min) / (max - min);
    const r = Math.round(255 * ratio);
    const b = Math.round(255 * (1 - ratio));
    return `rgb(${r}, 0, ${b})`;
  }


  return (
    <table style={{ borderCollapse: "collapse", display: "inline-table", border: "1px solid #ccc" }}>
      <thead>
        <tr>
          {/* Empty top-left corner */}
          <th style={{ width: 30, height: 30, border: '1px solid #ccc' }}></th>
          {colLabels.map((label, i) => (
            <th
              key={i}
              style={{
                width: 30,
                height: 30,
                border: '1px solid #ccc',
                fontSize: 10,
                writingMode: "vertical-rl",
                transform: "rotate(180deg)",
                textAlign: "center",
                padding: 2,
                userSelect: "none"
              }}
              title={label}
            >
              {label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {matrix.map((row, rowIndex) => (
          <tr key={rowIndex}>
            {/* Row label in first column */}
            <th
              style={{
                width: 30,
                height: 30,
                border: '1px solid #ccc',
                fontSize: 10,
                textAlign: "center",
                userSelect: "none",
                padding: 2,
              }}
              title={rowLabels[rowIndex] || ''}
            >
              {rowLabels[rowIndex]}
            </th>
            {row.map((value, colIndex) => (
              <td
                key={colIndex}
                style={{
                  width: 30,
                  height: 30,
                  backgroundColor: stdRange ? valueToColor(value) : valueToColor(value, min, max),
                  border: '1px solid #fff',
                  color: '#fff',
                  fontWeight: 'bold',
                  fontSize: 14,
                  textAlign: "center",
                  verticalAlign: "middle",
                  userSelect: "none",
                }}
                title={value}
              >
                {value}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Analysis() {

    const {streamedData} = useContext(MyContext);

    let callData_bs = [];
    let putData_bs = [];
    let callData_lm = [];
    let putData_lm = [];
    let callData_rv = [];
    let putData_rv = [];
    let callData_to = [];
    let putData_to = [];

    if (streamedData) {
        console.log('streameddata:'); console.log(streamedData);
        for (let i=0; i<streamedData.expiries.length; i++) {
            let thisrowCall_bs = [];
            let thisrowPut_bs = [];
            let thisrowCall_lm = [];
            let thisrowPut_lm = [];
            let thisrowCall_rv = [];
            let thisrowPut_rv = [];
            let thisrowCall_to = [];
            let thisrowPut_to = [];
            for (let j=0; j<streamedData.strikes.length; j++) {
                thisrowCall_bs.push(streamedData.buySellProbs[i][j][0]);
                thisrowPut_bs.push(streamedData.buySellProbs[i][j][1]);
                thisrowCall_lm.push(streamedData.limitMarketProbs[i][j][0]);
                thisrowPut_lm.push(streamedData.limitMarketProbs[i][j][1]);
                thisrowCall_rv.push(streamedData.recentVolume[i][j][0]);
                thisrowPut_rv.push(streamedData.recentVolume[i][j][1]);
                thisrowCall_to.push(streamedData.totalOrders[i][j][0]);
                thisrowPut_to.push(streamedData.totalOrders[i][j][1]);
            }
            callData_bs.push(thisrowCall_bs);
            putData_bs.push(thisrowPut_bs);
            callData_lm.push(thisrowCall_lm);
            putData_lm.push(thisrowPut_lm);
            callData_rv.push(thisrowCall_rv);
            putData_rv.push(thisrowPut_rv);
            callData_to.push(thisrowCall_to);
            putData_to.push(thisrowPut_to);
        }
    }

    return (
        <div>

            <div style={{display: "flex", flexDirection: "column", alignItems: "center", gap: "10px"}}>
            <GeneralInfo/>
            </div>

            {streamedData ? (
            <>
            <div style={{display: "flex", flexDirection: "column", alignItems: "center"}}>
              <div>Buy & Sell order distributions</div>
              <div>Greener = more sells, redder = more buys</div>
                <div style={{ display: "flex", gap: "10px", justifyContent: "center", marginBottom: "10px" }}>
                  <div className="Test" style={{display: "flex", flexDirection: "column", alignItems: "center"}}> Calls
                    <Heatmap matrix={callData_bs} colLabels={streamedData.strikes} rowLabels={streamedData.expiries} />
                  </div>
                  <div className="Test" style={{display: "flex", flexDirection: "column", alignItems: "center"}}> Puts
                    <Heatmap matrix={putData_bs} colLabels={streamedData.strikes} rowLabels={streamedData.expiries} />
                  </div>
                </div>
            </div>
            <div style={{display: "flex", flexDirection: "column", alignItems: "center"}}>
              <div>Limit & Market order distributions</div>
              <div>Greener = more limits, redder = more markets</div>
                <div style={{ display: "flex", gap: "10px", justifyContent: "center" }}>
                  <div className="Test" style={{display: "flex", flexDirection: "column", alignItems: "center"}}> Calls
                    <Heatmap matrix={callData_lm} colLabels={streamedData.strikes} rowLabels={streamedData.expiries} />
                  </div>
                  <div className="Test" style={{display: "flex", flexDirection: "column", alignItems: "center"}}> Puts
                    <Heatmap matrix={putData_lm} colLabels={streamedData.strikes} rowLabels={streamedData.expiries} />
                  </div>
                </div>
            </div>
            <div style={{display: "flex", flexDirection: "column", alignItems: "center"}}>
              Recent Volume
                <div className="test"style={{ display: "flex", gap: "10px", justifyContent: "center" }}>
                  <div className="Test" style={{display: "flex", flexDirection: "column", alignItems: "center"}}> Calls
                    <Heatmap matrix={callData_rv} colLabels={streamedData.strikes} rowLabels={streamedData.expiries} stdRange={false} />
                  </div>
                  <div className="Test" style={{display: "flex", flexDirection: "column", alignItems: "center"}}> Puts
                    <Heatmap matrix={putData_rv} colLabels={streamedData.strikes} rowLabels={streamedData.expiries} stdRange={false} />
                  </div>
                </div>
            </div>
            <div style={{display: "flex", flexDirection: "column", alignItems: "center"}}>
              Total orders
                <div style={{ display: "flex", gap: "10px", justifyContent: "center" }}>
                  <div className="Test" style={{display: "flex", flexDirection: "column", alignItems: "center"}}> Calls
                    <Heatmap matrix={callData_to} colLabels={streamedData.strikes} rowLabels={streamedData.expiries} stdRange={false}/>
                  </div>
                  <div className="Test" style={{display: "flex", flexDirection: "column", alignItems: "center"}}> Puts
                    <Heatmap matrix={putData_to} colLabels={streamedData.strikes} rowLabels={streamedData.expiries} stdRange={false}/>
                  </div>
                </div>
            </div>
            </>
            ) : (
            <div style={{display: "flex", flexDirection: "column", alignItems: "center"}}>No data here yet</div>
            )}


        </div>
    )
}

export default Analysis;
